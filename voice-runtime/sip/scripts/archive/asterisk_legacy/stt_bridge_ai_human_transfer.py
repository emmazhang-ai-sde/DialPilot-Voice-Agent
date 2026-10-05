"""
Step 2/3 -- Wire call audio into STT, and wire TTS output back into the call.

This file is a copy of Amy's `amy/llm-testing/agent-test6.py` (Modulate STT ->
Groq LLM -> Deepgram Aura TTS pipeline), adapted per
`design-docs-sip/sip-loop-mvp-step-by-step-guidence/step2-wire-call-audio-into-stt.md`
and `.../step3-wire-tts-output-into-call.md`. Two structural changes from
Amy's original, everything else (Modulate connection, transcript queue, Groq)
untouched:

- **Audio in (Step 2):** instead of a PyAudio mic stream, audio arrives as RTP
  from an Asterisk `externalMedia` channel (via sip/asterisk/verify_ari.py's ARI
  answer/Stasis pattern), gets stripped of its RTP header, and is queued for
  the same Modulate streaming connection Amy's original script already used.
- **Audio out (Step 3):** instead of playing Deepgram Aura's reply locally via
  `sounddevice`, the generated audio is written to a WAV file, downsampled for
  Asterisk with `ffmpeg`, copied into the `asterisk-mvp` container, and played
  into the live call via ARI's `/channels/{id}/play`.

Original attribution: Amy, amy/llm-testing/agent-test6.py.
"""

import os
import queue
import subprocess
import threading
from deepgram import DeepgramClient
from groq import Groq
from websockets.sync.client import connect as ws_connect
import json
import time

# --- STEP 2 ADDITION: ARI + RTP bridge imports (not in original agent-test6.py) ---
import socket as udp_socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests
from websocket import create_connection

from asterisk_streaming_output import (
    AsteriskStreamingOutputManager,
    AsteriskStreamingRouteConfig,
)
from runtime.agent_registry import AgentRegistry
from communication.call_session import CallSession
from runtime.capability_registry import CapabilityRegistry
from runtime.capability_executor import execute_capability_call
from rag.knowledge_base_registry import KnowledgeBaseRegistry
from runtime.context_builder import build_runtime_context
from runtime.capability_policy import (
    DEFAULT_MAX_TOOL_RESULT_CHARS,
    CapabilityCallBudgetExceeded,
    RuntimeCapabilityCallBudget,
    serialize_tool_result,
)
from livekit_runtime.tools import DialForgeToolHandlers
from livekit_runtime.turn_runner import (
    OpenAICompatibleTurnRunnerConfig,
    RuntimeCapabilityTurnRunner,
)
from voice_frame_bridge import BargeInDetectionConfig, LiveAudioFrameBridge
from voice_output_sink import (
    AriFilePlaybackConfig,
    AssistantSpeechHandle,
    OutputSinkUnavailable,
    StreamingWebSocketOutputConfig,
    create_output_sink,
)
from voice_provider_tuning import default_env_files, load_provider_tuning
from voice_runtime_frames import (
    AssistantTextFrame,
    UserTurnFrame,
    user_turn_frame_from_committed,
)
from voice_turn_state import BargeInDecision, BargeInGate, TurnCompletionGate

# set up timer for timestamps
_START = time.time()
def _ms():
    return int((time.time() - _START) * 1000)


_log_lock = threading.Lock()
SHOW_LLM_STREAM = os.environ.get("SHOW_LLM_STREAM") == "1"
ENABLE_RUNTIME_CAPABILITY_TOOLS = (
    os.environ.get("ENABLE_RUNTIME_CAPABILITY_TOOLS", "").strip().lower()
    in {"1", "true", "yes", "on"}
)
MAX_RUNTIME_TOOL_RESULT_CHARS = int(
    os.environ.get("MAX_RUNTIME_TOOL_RESULT_CHARS") or DEFAULT_MAX_TOOL_RESULT_CHARS
)


def log(tag, text="", ms=None, blank_before=0, blank_after=0, payload=None):
    """Thread-safe, single-line logger. Every worker must call this instead
    of print() -- concurrent bare prints (esp. groq_worker's raw token
    stream) is what caused interleaved garbage like
    "Yes, I hear you.TTS: Yes, I hear you." (see step3.3 doc). blank_before
    (int, also accepts True/False) marks the three headline latency
    checkpoints (STT final, LLM first-token, TTS audio) so a turn's phases
    are visually separated, and the end-of-call divider. blank_after
    separates the one-time call-setup block from the STT partial stream
    that follows it."""
    stamp = f" +{ms}ms" if ms is not None else ""
    line = f"[{tag}{stamp}] {text}" if text else f"[{tag}{stamp}]"
    with _log_lock:
        for _ in range(int(blank_before)):
            print()
        print(line, flush=True)
        for _ in range(int(blank_after)):
            print()
    event = {"tag": tag, "text": text, "ms": ms}
    if payload is not None:
        event["payload"] = payload
    _ui_queue.put(event)


# --- DEMO UI ADDITION (2026-07-10): mirror every log() line to the demo UI
# server (sip/demo-ui/demo_ui_server.py) so the browser renders the same
# event stream the terminal shows. Decoupled by a queue + daemon sender
# thread: if the UI server isn't running, each POST fails fast and the event
# is dropped -- the call loop never blocks or slows down because of the UI. ---
UI_EVENTS_URL = "http://localhost:8400/internal/events"
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 8500
_ui_queue = queue.Queue()


def _ui_sender():
    while True:
        event = _ui_queue.get()
        try:
            requests.post(UI_EVENTS_URL, json=event, timeout=0.5)
        except Exception:
            pass  # UI server down -- drop silently, never touch the pipeline


# --- DEMO UI ADDITION (2026-07-13): heartbeat so the UI can honestly tell
# "bridge running" from "bridge dead". Asterisk's ARI app registration lingers
# even after the bridge exits, so the UI can't rely on it -- a dead bridge
# looked "up" and the UI rang the softphone into a Stasis app with no handler,
# which Asterisk hangs up the instant the call is answered. A fresh heartbeat
# is the true liveness signal; the UI server refuses to place a call without one. ---
def _ui_heartbeat():
    while True:
        _ui_queue.put({"tag": "BRIDGE", "text": "online", "ms": None})
        time.sleep(10)


threading.Thread(target=_ui_sender, daemon=True).start()
threading.Thread(target=_ui_heartbeat, daemon=True).start()


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROVIDER_TUNING = load_provider_tuning(env_files=default_env_files(_SCRIPT_DIR))

# api keys
DEEPGRAM_KEY = PROVIDER_TUNING.deepgram_api_key
GROQ_KEY = PROVIDER_TUNING.groq_api_key
MODULATE_KEY = PROVIDER_TUNING.modulate_api_key

# fail loud if a required key is missing, rather than hitting a confusing
# 4003 (Modulate auth reject) or 401 deep inside a worker thread
_missing = [n for n, v in
            (("DEEPGRAM_API_KEY", DEEPGRAM_KEY),
             ("GROQ_API_KEY", GROQ_KEY),
             ("MODULATE_API_KEY", MODULATE_KEY)) if not v]
if _missing:
    print("WARNING: missing keys in .env.local:", ", ".join(_missing))

log("PROVIDER_TUNING", "loaded", payload=PROVIDER_TUNING.redacted_payload())

# setup parameters
RATE = PROVIDER_TUNING.modulate_sample_rate
CHANNELS = PROVIDER_TUNING.modulate_num_channels
TTS_SAMPLE_RATE = PROVIDER_TUNING.deepgram_tts_sample_rate

# --- STEP 2 ADDITION: ARI config (same as sip/asterisk/verify_ari.py) ---
ARI_HOST = "localhost:8088"
ARI_USER = "sip-mvp-user"
ARI_PASSWORD = "changeme_use_a_real_secret"
APP_NAME = "sip-mvp-app"

# --- STEP 2 ADDITION: externalMedia / RTP bridge config ---
# --- BUGFIX (2026-07-07): "127.0.0.1" here is resolved INSIDE the asterisk-mvp
# container (bridge network mode), so it pointed at the container's own
# loopback -- not this host, where rtp_listener() actually binds. Asterisk was
# sending RTP into its own void; zero packets ever reached UDP 9000 on the
# host, even with the caller speaking for 30+ seconds. host.docker.internal
# is Docker Desktop's DNS name for reaching the host from inside a container
# (confirmed resolvable from asterisk-mvp: `docker exec asterisk-mvp getent
# hosts host.docker.internal`).
#
# NOTE (2026-07-21): on some Docker Desktop setups host.docker.internal
# resolves IPv6-first to an unreachable address (fdc4:...::254) and Asterisk
# 500s the externalMedia create with "Could not get our address for sending
# media". If that happens, verify with:
#     docker exec asterisk-mvp getent ahostsv4 host.docker.internal
# and either hardcode the IPv4 it prints (typically 192.168.65.254) or fix
# the container's resolution. ---
EXTERNAL_MEDIA_HOST = "192.168.65.254:9000"
UDP_LISTEN_PORT = 9000
RTP_HEADER_LEN = 12

# --- STEP 3 ADDITION: TTS playback-into-call config ---
ASTERISK_CONTAINER = "asterisk-mvp"
SOUNDS_DIR_IN_CONTAINER = "/var/lib/asterisk/sounds/custom"
TTS_STAGING_DIR = "/tmp/sip-tts-staging"

# Set from StasisStart / cleared on StasisEnd -- single active call only,
# concurrency is explicitly out of scope for this MVP (step7-agent-roadmap.md, section 3)
current_channel_id = None

# --- MULTI-COMPANY ADDITION (2026-07-10): every business GlobiFYE serves has
# its own knowledge base + TTS voice, chosen per call by the number the caller
# dialed. The dialplan passes the company key as a Stasis() argument
# (Stasis(sip-mvp-app,pacificbeef) for 1000, ...,globifye for 2000); see
# extensions.conf [sip-mvp] and the step 5 demo-console doc. knowledge-base/
# companies.json is the shared source of truth -- the demo UI server reads the
# same file. ---
_KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "knowledge-base")

# Behavior rules shared by every company's agent -- only the identity line and
# the knowledge base below it change per company.
AGENT_RULES = (
    "Respond to the customer in a natural, spoken manner as if on a phone call. "
    "Keep answers as short as possible. If the customer raises concerns, acknowledge them "
    "politely and address them in a business-appropriate way. Be concise and conversational. "
    "Do not use any markdown formatting, bullet points, asterisks, or emojis. Do not output "
    "thinking, only the final answer (conversational response). Use plain natural language "
    "only, without filler openers, as your response will be read aloud by text-to-speech."
)


# Said whenever the agent has no grounded answer: KB/RAG doesn't cover the
# question, or the company has no knowledge base connected at all. Exact
# wording is a product decision (Shuyang, 2026-07-13) -- keep verbatim.
FALLBACK_LINE = (
    "I'm not sure I have the details you're looking for, but I can have a "
    "team member follow up with you. May I have your name and a phone number, please?"
)


# The agent is a sales rep. Each company's KB describes its product, pricing,
# and a five-stage sales pipeline (Prospect, Contact, Demo, Proposal, Closing);
# the prompt tells the agent to figure out the prospect's stage and move them
# to the next one. (Making that stage a tracked field on the contact + a
# post-call analysis output is a proposed follow-up: see step7 roadmap.)
SALES_PROCESS = (
    "Work the sales pipeline: figure out where the prospect is (Prospect, Contact, "
    "Demo, Proposal, Closing) and guide the conversation toward the next stage, using "
    "the playbook in the knowledge base. Ask the qualifying questions, handle objections "
    "with the responses provided, and always end with a clear next step."
)


def _build_system_prompt(display_name, kb_text):
    return {
        "role": "system",
        "content": (
            f"You are an AI sales representative for {display_name}, speaking with a prospect on a sales call. "
            f"{AGENT_RULES} {SALES_PROCESS} "
            f"Everything you know about {display_name}'s product, pricing, and process is in the knowledge "
            f"base below. Answer only from it -- never invent prices, product details, or terms. "
            f"If the prospect asks something the knowledge base does not cover, reply exactly: "
            f"\"{FALLBACK_LINE}\" and then collect their name and phone number.\n\n"
            f"--- {display_name} KNOWLEDGE BASE ---\n{kb_text}"
        ),
    }


def _build_fallback_prompt(display_name):
    """Used when a company has no knowledge base connected yet (no kb_file, or
    the file is missing/empty). The agent can greet and qualify at a high level,
    but every detail question gets the fallback line + contact capture.
    Once a KB (or later the RAG library) exists for the company, the loader
    below picks it up automatically and this prompt is not used."""
    return {
        "role": "system",
        "content": (
            f"You are an AI sales representative for {display_name}, speaking with a prospect on a sales call. "
            f"{AGENT_RULES} "
            f"You do not yet have a knowledge base for {display_name}, so you cannot answer any "
            f"question about the product, pricing, or terms. "
            f"For any such question, reply exactly: \"{FALLBACK_LINE}\" "
            f"Then collect the prospect's name and phone number, confirm them back, and let them "
            f"know a team member will follow up. Never invent details."
        ),
    }


def _load_companies():
    with open(os.path.join(_KB_DIR, "companies.json")) as f:
        companies = json.load(f)
    for c in companies.values():
        kb_text = ""
        kb_file = c.get("kb_file")
        if kb_file:
            try:
                with open(os.path.join(_KB_DIR, kb_file)) as kb:
                    kb_text = kb.read().strip()
            except FileNotFoundError:
                pass
        if kb_text:
            c["system_prompt"] = _build_system_prompt(c["display_name"], kb_text)
            c["kb_available"] = True
        else:
            c["system_prompt"] = _build_fallback_prompt(c["display_name"])
            c["kb_available"] = False
    return companies


COMPANIES = _load_companies()
DEFAULT_COMPANY = "pacificbeef"
AGENT_REGISTRY = AgentRegistry.from_legacy_company_data(COMPANIES)
KNOWLEDGE_BASE_REGISTRY = KnowledgeBaseRegistry.from_path(
    os.path.join(_KB_DIR, "knowledge_profiles.json")
)
CAPABILITY_REGISTRY = CapabilityRegistry.default()

# Set per call from StasisStart (single active call only, per MVP scope).
current_company = DEFAULT_COMPANY
current_voice = COMPANIES[DEFAULT_COMPANY]["voice"]
current_agent_config = AGENT_REGISTRY.get(DEFAULT_COMPANY)

MAX_HISTORY = 10
MAX_RUNTIME_TOOL_ROUNDS = 2

# Position 0 is always the active company's system prompt; the trim in
# groq_worker preserves it, so it survives regardless of which company is live.
conversation_history = [COMPANIES[DEFAULT_COMPANY]["system_prompt"]]
current_session = CallSession.from_agent(
    current_agent_config,
    call_session_id="legacy-single-call",
    conversation_history=conversation_history,
)

# clients
dg = DeepgramClient(api_key=DEEPGRAM_KEY)
client = Groq(api_key=GROQ_KEY)

# queues
transcript_queue = queue.Queue()
tts_queue = queue.Queue()
turn_gate = TurnCompletionGate(PROVIDER_TUNING.turn_config())
barge_in_gate = BargeInGate()
audio_frame_bridge = LiveAudioFrameBridge(
    input_sample_rate=RATE,
    input_num_channels=CHANNELS,
    tts_sample_rate=TTS_SAMPLE_RATE,
    should_suppress_input=turn_gate.is_input_suppressed,
    echo_tail_ms=PROVIDER_TUNING.turn_playback_echo_tail_ms,
    barge_in_detection_config=BargeInDetectionConfig(
        enabled=PROVIDER_TUNING.barge_in_detection_enabled,
        rms_threshold=PROVIDER_TUNING.barge_in_rms_threshold,
        min_audio_ms=PROVIDER_TUNING.barge_in_min_audio_ms,
        reset_gap_ms=PROVIDER_TUNING.barge_in_reset_gap_ms,
    ),
)
tts_playback_sink = None
streaming_output_manager = None
active_streaming_websocket_url = None
current_assistant_speech_handle = None
_assistant_speech_counter = 0

# --- STEP 2 CHANGE: audio now arrives via RTP from Asterisk's externalMedia
# channel instead of a PyAudio mic stream. rtp_listener() (below) populates
# this queue; modulate_worker()'s send_audio reads from it. ---
audio_queue = queue.Queue()


# concurrent workers
# --- STEP 2 CHANGE: was mic_worker(socket) reading a PyAudio mic_stream
# (dead code in agent-test6.py -- modulate_worker had its own inline mic read
# instead of calling this). Repurposed as the RTP ingestion side: listens on
# UDP for the externalMedia stream, strips the 12-byte RTP header, and queues
# the raw PCM payload for modulate_worker's send_audio. ---
def rtp_listener():
    global current_playback_id
    sock = udp_socket.socket(udp_socket.AF_INET, udp_socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_LISTEN_PORT))
    log("RTP", f"listening on UDP {UDP_LISTEN_PORT}")
    first = True
    while True:
        packet, _ = sock.recvfrom(2048)
        if first:
            log("RTP", f"first packet received ({len(packet)} bytes)")
            first = False
        raw = packet[RTP_HEADER_LEN:]
        frame = audio_frame_bridge.input_frame_from_rtp_payload(raw)
        suppression_reason = current_input_suppression_reason()
        candidate = audio_frame_bridge.detect_barge_in_candidate(frame)
        if candidate:
            decision = barge_in_gate.decide_audio_candidate(
                candidate,
                suppression_reason=suppression_reason,
            )
            if _interrupt_current_ai_audio(
                decision=decision,
                candidate=candidate,
                barge_in=True,
            ):
                audio_frame_bridge.reset_barge_in_candidate()
                audio_queue.put(frame.audio)
                continue
            log(
                "BARGE_IN",
                "audio candidate suppressed",
                payload={
                    "reason": decision.reason,
                    "suppression_reason": suppression_reason,
                    "audio_rms": candidate.audio_rms,
                    "barge_in_audio_ms": candidate.accumulated_audio_ms,
                    "rms_threshold": candidate.threshold,
                    "min_audio_ms": candidate.min_audio_ms,
                },
            )
        if audio_frame_bridge.should_forward_input_frame(frame):
            audio_queue.put(frame.audio)


# LLM worker - Groq [GPT OSS 120B]
def groq_worker():
    global conversation_history

    while True:
        user_turn_frame = transcript_queue.get()
        if not isinstance(user_turn_frame, UserTurnFrame):
            user_turn_frame = UserTurnFrame(text=str(user_turn_frame), epoch=epoch)
        transcript = user_turn_frame.text

        # --- TRANSFER: human is live -- transcript still logged upstream, but
        # don't feed the LLM or generate a reply. ---
        if holder == "human":
            current_session.skip_ai_turn(transcript, source="groq_worker")
            log("SKIP_TURN", "owner is HUMAN; AI is listening but not responding", payload=current_session.room_debug_payload())
            continue

        turn_epoch = user_turn_frame.epoch
        if turn_epoch != epoch:
            log(
                "SKIP_TURN",
                "stale user turn frame; epoch changed before LLM turn",
                payload={"frame_epoch": turn_epoch, "current_epoch": epoch},
            )
            continue

        conversation_history.append({
            "role": "user",
            "content": transcript
        })
        current_session.conversation_history = conversation_history
        runtime_context = _record_runtime_context(source="llm_turn")
        turn_runner = _build_runtime_turn_runner(runtime_context)
        _record_runtime_turn_runner_exposure(turn_runner, runtime_context)

        result = turn_runner.run(
            conversation_history,
            on_first_token=lambda: log("LLM first-token", ms=_ms(), blank_before=True),
            on_sentence=lambda sentence: enqueue_assistant_text(sentence, turn_epoch),
            should_continue=lambda: turn_epoch == epoch,
        )
        _record_runtime_turn_runner_events(result.events)
        current_session.conversation_history = conversation_history

        if result.fallback_used:
            log(
                "CAPABILITY_TOOLS",
                "tool round limit reached; skipping additional model call",
            )

        log("LLM reply", result.assistant_text, ms=_ms())

        if len(conversation_history) > MAX_HISTORY + 1:
            conversation_history = (
                [conversation_history[0]] + conversation_history[-(MAX_HISTORY):]
            )
            current_session.conversation_history = conversation_history


def play_deepgram(text):
    global current_playback_id, current_assistant_speech_handle

    if current_channel_id is None:
        log("TTS", f"no active call channel, skipping playback for: {text}")
        return

    speech_handle = new_assistant_speech_handle()
    current_assistant_speech_handle = speech_handle

    streaming_output = is_streaming_output_sink()
    if streaming_output:
        turn_gate.on_playback_started(speech_handle.turn_id)
        audio_frame_bridge.mark_ai_speaking()
        output_frames = iter_deepgram_output_frames(text)
    else:
        output_frames = list(iter_deepgram_output_frames(text))
    try:
        result = get_tts_playback_sink().play(
            frames=output_frames,
            channel_id=current_channel_id,
            speech_handle=speech_handle,
        )
    except OutputSinkUnavailable as exc:
        log("TTS", f"output sink unavailable: {exc}")
        raise
    if result is None:
        log("TTS", "no audio frames generated; skipping playback")
        if streaming_output:
            turn_gate.on_playback_interrupted(speech_handle.turn_id)
            audio_frame_bridge.mark_ai_interrupted()
        current_assistant_speech_handle = None
        return

    current_playback_id = result.playback_id
    current_session.set_playback(current_playback_id)
    if current_playback_id:
        turn_gate.on_playback_started(current_playback_id)
        audio_frame_bridge.mark_ai_speaking()
    elif streaming_output:
        if result.interrupted:
            turn_gate.on_playback_interrupted(speech_handle.turn_id)
            audio_frame_bridge.mark_ai_interrupted()
        else:
            turn_gate.on_playback_finished(speech_handle.turn_id)
            audio_frame_bridge.mark_ai_done_speaking()
        current_assistant_speech_handle = None
    log("TTS played", result.sound_name, ms=_ms())


def iter_deepgram_output_frames(text):
    first = True
    for chunk in dg.speak.v1.audio.generate(
        text=text,
        model=current_voice,  # MULTI-COMPANY: per-call voice set on StasisStart
        encoding=PROVIDER_TUNING.deepgram_tts_encoding,
        sample_rate=TTS_SAMPLE_RATE,
        container=PROVIDER_TUNING.deepgram_tts_container,
    ):
        if first:
            log("TTS audio", ms=_ms(), blank_before=True)
            first = False
        yield audio_frame_bridge.output_frame_from_tts_chunk(chunk)


def new_assistant_speech_handle():
    global _assistant_speech_counter
    _assistant_speech_counter += 1
    return AssistantSpeechHandle(
        turn_id=f"assistant-speech-{_assistant_speech_counter}",
        epoch=epoch,
    )


def is_streaming_output_sink():
    return PROVIDER_TUNING.tts_output_sink.strip().lower() in {
        "streaming",
        "streaming_websocket",
    }


def enqueue_assistant_text(text, turn_epoch):
    tts_queue.put(AssistantTextFrame(text=text, epoch=turn_epoch))


# TTS worker - Deepgram Aura
def tts_worker():
    while True:
        assistant_text_frame = tts_queue.get()
        if isinstance(assistant_text_frame, AssistantTextFrame):
            text = assistant_text_frame.text
            turn_epoch = assistant_text_frame.epoch
        else:
            text, turn_epoch = assistant_text_frame
        if turn_epoch != epoch or holder == "human":
            continue  # stale turn or human took over -- drop silently
        log("TTS gen", text)
        play_deepgram(text)


def turn_gate_worker():
    while True:
        committed = turn_gate.tick()
        if committed:
            transcript_queue.put(user_turn_frame_from_committed(committed, epoch=epoch))
            log(
                "TURN commit",
                committed.transcript,
                ms=_ms(),
                payload={
                    "segments": list(committed.segments),
                    "silence_ms": committed.silence_ms,
                    "semantic_kind": committed.semantic_kind,
                    "semantic_reason": committed.semantic_reason,
                },
            )
        time.sleep(0.05)


# STT worker - Modulate.ai
def _modulate_url():
    return PROVIDER_TUNING.modulate_url()


def _modulate_session(first_chunk):
    """One Modulate streaming connection: send audio + read transcripts until
    the socket closes. Raises on close/error so modulate_worker can reconnect."""
    with ws_connect(_modulate_url()) as ws:
        ws.send(first_chunk)
        stop = threading.Event()

        def send_audio():
            while not stop.is_set():
                try:
                    chunk = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue  # wake periodically to re-check stop
                try:
                    ws.send(chunk)
                except Exception:
                    stop.set()
                    return

        send_thread = threading.Thread(target=send_audio, daemon=True)
        send_thread.start()
        # starts True so the first partial of the call also gets its blank
        # line; reset to True after each STT final so the next utterance's
        # partial stream starts with a gap too (see step3.3 doc, Decision 8)
        first_partial_of_utterance = True
        try:
            for message in ws:
                if isinstance(message, bytes):
                    continue
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "partial_utterance":
                    partial_text = data.get("partial_utterance", {}).get("text", "").strip()
                    if partial_text:
                        if turn_gate.on_partial(partial_text):
                            log("STT partial", partial_text, blank_before=first_partial_of_utterance)
                            first_partial_of_utterance = False
                        else:
                            if handle_suppressed_stt_barge_in(
                                partial_text,
                                event="partial_utterance",
                            ):
                                if turn_gate.on_partial(partial_text):
                                    log(
                                        "STT partial",
                                        partial_text,
                                        blank_before=first_partial_of_utterance,
                                    )
                                    first_partial_of_utterance = False
                            else:
                                log(
                                    "STT suppressed",
                                    partial_text,
                                    payload={
                                        "event": "partial_utterance",
                                        "reason": current_input_suppression_reason(),
                                    },
                                )

                elif msg_type == "utterance":
                    text = data.get("utterance", {}).get("text", "").strip()
                    if text:
                        if turn_gate.on_final(text):
                            log("STT final", text, ms=_ms(), blank_before=True)
                        else:
                            if handle_suppressed_stt_barge_in(text, event="utterance"):
                                if turn_gate.on_final(text):
                                    log("STT final", text, ms=_ms(), blank_before=True)
                            else:
                                log(
                                    "STT suppressed",
                                    text,
                                    ms=_ms(),
                                    payload={
                                        "event": "utterance",
                                        "reason": current_input_suppression_reason(),
                                    },
                                )
                        first_partial_of_utterance = True
        finally:
            stop.set()
            send_thread.join(timeout=1)


def modulate_worker():
    # --- BUGFIX (2026-07-07): the connection was opened once at startup and
    # then sat idle until a call arrived. Modulate closes idle streaming
    # connections (observed: ConnectionClosedOK code 1000), so the first call's
    # audio hit a dead socket and nothing ever reconnected. Instead: block until
    # audio actually starts (a call is live), connect *then*, and reconnect for
    # each subsequent call. No idle socket to time out. ---
    while True:
        first_chunk = audio_queue.get()  # blocks until a call streams audio
        try:
            _modulate_session(first_chunk)
        except Exception as e:
            turn_gate.reset_pending()
            log("STT", f"session ended ({type(e).__name__}); reconnecting on next call")


# --- STEP 2 ADDITION: ARI control -- answers the call and bridges it with a
# new externalMedia channel so Asterisk starts forwarding RTP to
# UDP_LISTEN_PORT. Mirrors sip/asterisk/verify_ari.py's StasisStart/answer pattern. ---
def ari_post(path, **params):
    resp = requests.post(
        f"http://{ARI_HOST}/ari{path}",
        params=params,
        auth=(ARI_USER, ARI_PASSWORD),
    )
    resp.raise_for_status()
    return resp.json() if resp.text else None


def get_tts_playback_sink():
    global tts_playback_sink
    streaming_url = PROVIDER_TUNING.tts_streaming_websocket_url
    if not streaming_url:
        streaming_url = current_session.output_stream_url or active_streaming_websocket_url or ""

    if is_streaming_output_sink():
        return create_output_sink(
            sink_name=PROVIDER_TUNING.tts_output_sink,
            ari_config=AriFilePlaybackConfig(
                staging_dir=TTS_STAGING_DIR,
                asterisk_container=ASTERISK_CONTAINER,
                sounds_dir_in_container=SOUNDS_DIR_IN_CONTAINER,
                playback_sample_rate=PROVIDER_TUNING.asterisk_playback_sample_rate,
            ),
            ari_post=ari_post,
            streaming_config=StreamingWebSocketOutputConfig(
                websocket_url=streaming_url,
                sample_rate=PROVIDER_TUNING.tts_streaming_sample_rate,
                num_channels=PROVIDER_TUNING.tts_streaming_num_channels,
            ),
            websocket_connect=connect_tts_streaming_transport,
        )

    if tts_playback_sink is None:
        tts_playback_sink = create_output_sink(
            sink_name=PROVIDER_TUNING.tts_output_sink,
            ari_config=AriFilePlaybackConfig(
                staging_dir=TTS_STAGING_DIR,
                asterisk_container=ASTERISK_CONTAINER,
                sounds_dir_in_container=SOUNDS_DIR_IN_CONTAINER,
                playback_sample_rate=PROVIDER_TUNING.asterisk_playback_sample_rate,
            ),
            ari_post=ari_post,
        )
    return tts_playback_sink


def connect_tts_streaming_transport(websocket_url):
    if streaming_output_manager and streaming_output_manager.owns_websocket_url(websocket_url):
        return streaming_output_manager.connect_transport(websocket_url)
    return create_connection(websocket_url)


def current_input_suppression_reason():
    frame_reason = audio_frame_bridge.input_suppression_reason()
    turn_reason = turn_gate.input_suppression_reason()
    if frame_reason == "external_input_suppression":
        return turn_reason or frame_reason
    return frame_reason or turn_reason


def handle_suppressed_stt_barge_in(text, *, event):
    suppression_reason = current_input_suppression_reason()
    decision = barge_in_gate.decide_transcript(
        text,
        suppression_reason=suppression_reason,
    )
    if _interrupt_current_ai_audio(
        decision=decision,
        transcript=text,
        barge_in=True,
    ):
        return True
    log(
        "BARGE_IN",
        "suppressed STT did not interrupt",
        payload={
            "event": event,
            "reason": decision.reason,
            "suppression_reason": suppression_reason,
            "text": decision.text,
        },
    )
    return False


def confirm_barge_in_candidate(candidate):
    decision = barge_in_gate.decide_audio_candidate(
        candidate,
        suppression_reason=current_input_suppression_reason(),
    )
    return _interrupt_current_ai_audio(
        decision=decision,
        candidate=candidate,
        barge_in=True,
    )


def _interrupt_current_ai_audio(
    *,
    decision: BargeInDecision,
    candidate=None,
    transcript=None,
    barge_in=False,
):
    global current_playback_id, current_assistant_speech_handle
    if not decision.should_interrupt:
        return False
    with _call_control_lock:
        speech_handle = current_assistant_speech_handle
        if speech_handle:
            speech_handle.cancel()
        playback_id = current_playback_id
        playback_marker = playback_id or (speech_handle.turn_id if speech_handle else None)
        if barge_in:
            turn_gate.on_barge_in_confirmed(playback_marker)
        else:
            turn_gate.on_playback_interrupted(playback_marker)
        audio_frame_bridge.mark_ai_interrupted()
        flushed = False
        if streaming_output_manager and streaming_output_manager.session:
            try:
                flushed = streaming_output_manager.flush_current()
            except Exception as exc:
                log(
                    "BARGE_IN",
                    f"streaming flush failed ({type(exc).__name__}: {exc})",
                )
        if playback_id:
            ari_delete(f"/playbacks/{playback_id}")
            current_playback_id = None
            current_session.clear_playback()
        current_assistant_speech_handle = None
        payload = {
            "reason": decision.reason,
            "suppression_reason": decision.suppression_reason,
            "transcript": transcript,
            "playback_id": playback_id,
            "assistant_turn_id": speech_handle.turn_id if speech_handle else None,
            "streaming_flushed": flushed,
            "barge_in": barge_in,
        }
        if candidate is not None:
            payload.update(
                {
                    "audio_rms": candidate.audio_rms,
                    "barge_in_audio_ms": candidate.accumulated_audio_ms,
                    "rms_threshold": candidate.threshold,
                    "min_audio_ms": candidate.min_audio_ms,
                }
            )
        log(
            "BARGE_IN",
            "confirmed",
            payload=payload,
        )
        return True


def ari_delete(path):
    """Best-effort ARI delete -- used to tear down the bridge + externalMedia
    channel when a call ends, so they don't leak (see StasisEnd cleanup)."""
    try:
        requests.delete(
            f"http://{ARI_HOST}/ari{path}",
            auth=(ARI_USER, ARI_PASSWORD),
            timeout=3,
        )
    except requests.RequestException:
        pass


def get_streaming_output_manager():
    global streaming_output_manager
    if streaming_output_manager is None:
        streaming_output_manager = AsteriskStreamingOutputManager(
            config=AsteriskStreamingRouteConfig(
                static_websocket_url=PROVIDER_TUNING.tts_streaming_websocket_url,
                asterisk_endpoint=PROVIDER_TUNING.tts_streaming_asterisk_endpoint,
                incoming_base_url=PROVIDER_TUNING.tts_streaming_incoming_base_url,
                media_server_host=PROVIDER_TUNING.tts_streaming_server_host,
                media_server_port=PROVIDER_TUNING.tts_streaming_server_port,
                media_server_path=PROVIDER_TUNING.tts_streaming_server_path,
                transport_wait_timeout_ms=(
                    PROVIDER_TUNING.tts_streaming_transport_wait_timeout_ms
                ),
                app_name=APP_NAME,
            ),
            ari_post=ari_post,
            ari_delete=ari_delete,
        )
    return streaming_output_manager


def start_streaming_output_route(bridge_id):
    global active_streaming_websocket_url
    if not is_streaming_output_sink():
        return None
    session = get_streaming_output_manager().start(bridge_id=bridge_id)
    if session is None:
        active_streaming_websocket_url = None
        current_session.clear_output_stream()
        log(
            "STREAMING_OUTPUT",
            "no websocket route configured; streaming sink will fail until a URL is available",
        )
        return None
    active_streaming_websocket_url = session.websocket_url
    current_session.set_output_stream(
        stream_url=session.websocket_url,
        channel_id=session.output_channel_id,
    )
    if session.output_channel_id:
        _streaming_output_channel_ids.add(session.output_channel_id)
    log(
        "STREAMING_OUTPUT",
        "route ready",
        payload={
            "websocket_url_configured": bool(active_streaming_websocket_url),
            "output_channel_id": session.output_channel_id,
            "bridge_id": session.bridge_id,
        },
    )
    return session


def stop_streaming_output_route():
    global active_streaming_websocket_url
    if streaming_output_manager and streaming_output_manager.session:
        output_channel_id = streaming_output_manager.session.output_channel_id
        if output_channel_id:
            _streaming_output_channel_ids.discard(output_channel_id)
        streaming_output_manager.stop()
    active_streaming_websocket_url = None
    current_session.clear_output_stream()


# --- BUGFIX (2026-07-13): every call used to leak its mixing bridge + its
# externalMedia channel -- StasisEnd only cleared current_channel_id and never
# tore them down, so orphaned UnicastRTP channels/bridges piled up in the
# Stasis app for days (16 found). Track this call's bridge + externalMedia
# channel so StasisEnd can delete them. ---
current_bridge_id = None
current_ext_channel_id = None


# --- BUGFIX (2026-07-07): externalMedia channels join the same Stasis app
# (`app=APP_NAME`) a real caller does, so creating one fires its own
# StasisStart. Without this set, ari_event_loop treated every externalMedia
# channel as a brand-new call and bridged it to *another* externalMedia
# channel -- cascading indefinitely (.43 -> .44 -> .45 -> ...) until Asterisk
# rejected an addChannel call with a 422, leaving dozens of orphaned
# channels/bridges. Track our own externalMedia channel IDs so their
# StasisStart is recognized and skipped, not treated as a new call. ---
_external_media_channel_ids = set()
_streaming_output_channel_ids = set()

# --- TRANSFER (step 1): same idea for the salesperson leg -- we originate it
# ourselves into the same mixing bridge, muted. Its StasisStart must be
# recognized and NOT treated as a new inbound call, so track its channel id
# in _sales_channel_ids. `current_sales_channel_id` is what set_holder()
# targets for mute/unmute. ---
_sales_channel_ids = set()
_human_channel_hangup_causes = {}
current_sales_channel_id = None
DEFAULT_HUMAN_ENDPOINT = "PJSIP/sales-endpoint"
DEFAULT_HUMAN_CALLER_ID = "Sales"

# --- TRANSFER (step 2): holder switch. `holder` decides who is audible;
# everything (sales mute, LLM gating, TTS suppression) derives from it. `epoch`
# is bumped on every switch so an in-flight turn started under the old holder
# is discarded rather than played. `current_playback_id` lets a switch cut off
# the AI mid-sentence via DELETE /playbacks/{id}. ---
holder = "ai"                  # "ai" | "human"
epoch = 0
current_playback_id = None
_call_control_lock = threading.RLock()


def _build_active_runtime_context():
    """Build the new runtime vocabulary from the currently active call."""
    return build_runtime_context(
        agent=current_agent_config,
        session=current_session,
        knowledge_base_registry=KNOWLEDGE_BASE_REGISTRY,
        default_human_endpoint=DEFAULT_HUMAN_ENDPOINT,
        human_caller_id=DEFAULT_HUMAN_CALLER_ID,
    )


def _runtime_context_debug_payload(runtime_context):
    return {
        "agent_config_id": runtime_context.agent_config_id,
        "company_key": runtime_context.company_key,
        "call_session_id": runtime_context.call_session_id,
        "owner": runtime_context.owner,
        "current_stage": runtime_context.current_stage,
        "stage_transitions": [
            transition.name for transition in runtime_context.stage_transitions
        ],
        "knowledge_profiles": [
            knowledge_base.knowledge_profile_id
            for knowledge_base in runtime_context.knowledge_bases
        ],
        "human_handoff_enabled": bool(
            runtime_context.session_state.get("human_handoff_enabled")
        ),
        "default_human_endpoint": runtime_context.session_state.get(
            "default_human_endpoint"
        ),
    }


def _record_runtime_context(*, source):
    """Record RuntimeContext without changing the current LLM/tool behavior."""
    try:
        runtime_context = _build_active_runtime_context()
    except Exception as exc:
        log(
            "RUNTIME_CONTEXT",
            f"failed to build from active call: {type(exc).__name__}: {exc}",
        )
        return None

    payload = _runtime_context_debug_payload(runtime_context)
    current_session.append_event(
        "runtime_context.built",
        source=source,
        **payload,
    )
    return runtime_context


def _build_runtime_turn_runner(runtime_context):
    return RuntimeCapabilityTurnRunner(
        client=client,
        runtime_context=runtime_context,
        handlers=DialForgeToolHandlers(
            human_handoff_handler=_runtime_human_handoff_handler,
        ),
        registry=CAPABILITY_REGISTRY,
        tools_enabled=ENABLE_RUNTIME_CAPABILITY_TOOLS,
        config=OpenAICompatibleTurnRunnerConfig(
            model="openai/gpt-oss-120b",
            max_tool_rounds=MAX_RUNTIME_TOOL_ROUNDS,
            max_tool_result_chars=MAX_RUNTIME_TOOL_RESULT_CHARS,
            show_stream=SHOW_LLM_STREAM,
        ),
    )


def _record_runtime_turn_runner_exposure(turn_runner, runtime_context):
    if not ENABLE_RUNTIME_CAPABILITY_TOOLS or runtime_context is None:
        return

    tool_names = turn_runner.tool_names
    current_session.append_event(
        "runtime_capability_tools.exposed",
        enabled=True,
        tool_names=tool_names,
        agent_config_id=runtime_context.agent_config_id,
        company_key=runtime_context.company_key,
        call_session_id=runtime_context.call_session_id,
        owner=runtime_context.owner,
    )
    log(
        "CAPABILITY_TOOLS",
        f"exposed {len(tool_names)} tool(s)",
        payload={"tool_names": tool_names},
    )


def _record_runtime_turn_runner_events(events):
    for event in events:
        current_session.append_event(event.name, **event.payload)
        if event.name == "runtime_capability_tool_calls.dispatching":
            tool_calls = event.payload.get("tool_calls") or []
            log(
                "CAPABILITY_TOOLS",
                f"dispatching {len(tool_calls)} tool call(s)",
                payload={"tool_calls": tool_calls},
            )
        elif event.name == "runtime_capability_tool_call.failed":
            log(
                "CAPABILITY_TOOLS",
                f"tool call failed: {event.payload.get('error')}",
                payload={
                    "tool_call_id": event.payload.get("tool_call_id"),
                    "name": event.payload.get("capability"),
                },
            )
        elif event.name == "runtime_capability_tools.failed":
            log(
                "CAPABILITY_TOOLS",
                f"failed to expose tools: {event.payload.get('error')}",
            )
        elif event.name == "runtime_capability_policy.failed":
            log(
                "CAPABILITY_TOOLS",
                f"failed to build call budget: {event.payload.get('error')}",
            )


def _runtime_capability_model_kwargs(runtime_context):
    """Return model kwargs for capability tools when the rollout flag is on."""
    if not ENABLE_RUNTIME_CAPABILITY_TOOLS or runtime_context is None:
        return {}

    try:
        tools = CAPABILITY_REGISTRY.to_llm_tools(runtime_context)
    except Exception as exc:
        current_session.append_event(
            "runtime_capability_tools.failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        log(
            "CAPABILITY_TOOLS",
            f"failed to expose tools: {type(exc).__name__}: {exc}",
        )
        return {}

    tool_names = [
        tool.get("function", {}).get("name")
        for tool in tools
        if tool.get("function", {}).get("name")
    ]
    current_session.append_event(
        "runtime_capability_tools.exposed",
        enabled=True,
        tool_names=tool_names,
        agent_config_id=runtime_context.agent_config_id,
        company_key=runtime_context.company_key,
        call_session_id=runtime_context.call_session_id,
        owner=runtime_context.owner,
    )
    log(
        "CAPABILITY_TOOLS",
        f"exposed {len(tool_names)} tool(s)",
        payload={"tool_names": tool_names},
    )

    if not tools:
        return {}
    return {"tools": tools}


def _runtime_capability_call_budget(runtime_context):
    if not ENABLE_RUNTIME_CAPABILITY_TOOLS or runtime_context is None:
        return None
    try:
        return RuntimeCapabilityCallBudget.from_capabilities(
            CAPABILITY_REGISTRY.allowed_for(runtime_context)
        )
    except Exception as exc:
        current_session.append_event(
            "runtime_capability_policy.failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        log(
            "CAPABILITY_TOOLS",
            f"failed to build call budget: {type(exc).__name__}: {exc}",
        )
        return None


def _dispatch_runtime_tool_calls(
    *,
    runtime_context,
    tool_calls,
    tool_budget=None,
    assistant_content="",
):
    global conversation_history
    pending_tool_calls = _normalized_tool_calls(tool_calls)
    current_session.append_event(
        "runtime_capability_tool_calls.dispatching",
        tool_calls=pending_tool_calls,
        call_session_id=getattr(runtime_context, "call_session_id", None),
        company_key=getattr(runtime_context, "company_key", None),
    )
    log(
        "CAPABILITY_TOOLS",
        f"dispatching {len(pending_tool_calls)} tool call(s)",
        payload={
            "tool_calls": [
                {
                    "id": call.get("id"),
                    "name": call.get("name"),
                    "arguments": call.get("arguments"),
                }
                for call in pending_tool_calls
            ]
        },
    )

    assistant_message = {
        "role": "assistant",
        "tool_calls": [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": call["arguments"],
                },
            }
            for call in pending_tool_calls
        ],
    }
    if assistant_content:
        assistant_message["content"] = assistant_content
    conversation_history.append(assistant_message)

    for call in pending_tool_calls:
        result = _execute_runtime_tool_call(runtime_context, call, tool_budget=tool_budget)
        content, truncated, original_char_count = serialize_tool_result(
            result,
            max_chars=MAX_RUNTIME_TOOL_RESULT_CHARS,
        )
        if truncated:
            current_session.append_event(
                "runtime_capability_tool_result.truncated",
                tool_call_id=call["id"],
                capability=call["name"],
                original_char_count=original_char_count,
                max_char_count=MAX_RUNTIME_TOOL_RESULT_CHARS,
                serialized_char_count=len(content),
            )
        conversation_history.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "content": content,
        })
    current_session.conversation_history = conversation_history


def _normalized_tool_calls(tool_calls):
    normalized = []
    for index, call in sorted(tool_calls.items()):
        name = (call.get("name") or "").strip() or "unknown_capability"
        normalized.append({
            "id": call.get("id") or f"runtime_tool_call_{index}",
            "name": name,
            "arguments": call.get("arguments") or "{}",
        })
    return normalized


def _execute_runtime_tool_call(runtime_context, call, *, tool_budget=None):
    if runtime_context is None:
        return {
            "ok": False,
            "capability": call.get("name"),
            "error": "RuntimeContext is not available for this tool call.",
        }

    budget_payload = None
    try:
        if tool_budget is not None:
            budget_payload = tool_budget.reserve(call.get("name"))
        arguments = _parse_tool_arguments(call.get("arguments"))
        result = execute_capability_call(
            runtime_context,
            call.get("name"),
            arguments,
            registry=CAPABILITY_REGISTRY,
            human_handoff_handler=_runtime_human_handoff_handler,
        )
        current_session.append_event(
            "runtime_capability_tool_call.executed",
            tool_call_id=call.get("id"),
            capability=call.get("name"),
            ok=True,
            budget=budget_payload,
        )
        return result
    except CapabilityCallBudgetExceeded as exc:
        error = f"{type(exc).__name__}: {exc}"
        current_session.append_event(
            "runtime_capability_tool_call.failed",
            tool_call_id=call.get("id"),
            capability=call.get("name"),
            error=error,
            policy="max_calls_per_turn",
            budget=budget_payload,
        )
        log(
            "CAPABILITY_TOOLS",
            f"tool call blocked by policy: {error}",
            payload={"tool_call_id": call.get("id"), "name": call.get("name")},
        )
        return {
            "ok": False,
            "capability": call.get("name"),
            "error": error,
            "policy": "max_calls_per_turn",
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        current_session.append_event(
            "runtime_capability_tool_call.failed",
            tool_call_id=call.get("id"),
            capability=call.get("name"),
            error=error,
            budget=budget_payload,
        )
        log(
            "CAPABILITY_TOOLS",
            f"tool call failed: {error}",
            payload={"tool_call_id": call.get("id"), "name": call.get("name")},
        )
        return {
            "ok": False,
            "capability": call.get("name"),
            "error": error,
        }


def _parse_tool_arguments(raw_arguments):
    if raw_arguments is None or raw_arguments == "":
        return {}
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid tool arguments JSON: {exc}") from exc
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must decode to an object")
    return arguments


def _runtime_human_handoff_handler(
    *,
    context,
    reason,
    urgency,
    preferred_team,
    endpoint,
    caller_id,
):
    endpoint = endpoint or DEFAULT_HUMAN_ENDPOINT
    caller_id = caller_id or DEFAULT_HUMAN_CALLER_ID

    if current_sales_channel_id or current_session.human_invite_status:
        return {
            "invite_status": current_session.human_invite_status,
            "channel_id": current_sales_channel_id or current_session.human_channel_id,
            "already_invited": True,
            "endpoint": current_session.human_endpoint or endpoint,
            "caller_id": current_session.human_caller_id or caller_id,
            "reason": reason,
            "urgency": urgency,
            "preferred_team": preferred_team,
        }

    channel_id = invite_human_to_room(endpoint, caller_id=caller_id)
    return {
        "invite_status": current_session.human_invite_status,
        "channel_id": channel_id,
        "already_invited": False,
        "endpoint": endpoint,
        "caller_id": caller_id,
        "reason": reason,
        "urgency": urgency,
        "preferred_team": preferred_team,
    }


def create_asterisk_room(caller_channel_id):
    """Create the Asterisk equivalent of a Telnyx room for this call."""
    global current_bridge_id, current_ext_channel_id
    bridge = ari_post("/bridges", type="mixing")
    bridge_id = bridge["id"]
    ari_post(f"/bridges/{bridge_id}/addChannel", channel=caller_channel_id)

    ext_channel = ari_post(
        "/channels/externalMedia",
        app=APP_NAME,
        external_host=EXTERNAL_MEDIA_HOST,
        format="slin16",
    )
    _external_media_channel_ids.add(ext_channel["id"])
    ari_post(f"/bridges/{bridge_id}/addChannel", channel=ext_channel["id"])
    # Remember them so StasisEnd can tear them down instead of leaking.
    current_bridge_id = bridge_id
    current_ext_channel_id = ext_channel["id"]
    current_session.set_room(bridge_id=bridge_id, ai_media_channel_id=ext_channel["id"])
    start_streaming_output_route(bridge_id)
    log("ROOM", "created", payload=current_session.room_debug_payload())
    log("CALL", f"bridged {caller_channel_id} + externalMedia {ext_channel['id']} into bridge {bridge_id}")
    return bridge_id, ext_channel["id"]


def invite_human_to_room(endpoint, *, caller_id=DEFAULT_HUMAN_CALLER_ID):
    """Invite a human participant into the active Asterisk room."""
    global current_sales_channel_id
    # --- TRANSFER (step 1): originate the salesperson leg into the SAME bridge,
    # muted. Ringing/answer is async -- the actual addChannel + mute happen when
    # this channel's StasisStart fires (handled in ari_event_loop). Tracked in
    # _sales_channel_ids so its StasisStart is NOT treated as a new inbound call. ---
    try:
        sales = ari_post(
            "/channels",
            endpoint=endpoint,
            app=APP_NAME,
            callerId=caller_id,
        )
    except requests.RequestException as e:
        mark_handoff_failure(
            status="failed",
            reason=f"human originate failed: {type(e).__name__}: {e}",
            source="invite_human_to_room",
        )
        return None
    _sales_channel_ids.add(sales["id"])
    current_sales_channel_id = sales["id"]
    current_session.invite_human(
        endpoint=endpoint,
        caller_id=caller_id,
        channel_id=sales["id"],
    )
    log("HUMAN_INVITE", "ringing", payload=current_session.room_debug_payload())
    log("SALES", f"originating human leg {sales['id']} to {endpoint} (ringing, will join muted)")
    return sales["id"]


def invite_default_human_to_room():
    invite_human_to_room(DEFAULT_HUMAN_ENDPOINT, caller_id=DEFAULT_HUMAN_CALLER_ID)


def bridge_call_to_external_media(caller_channel_id):
    """Compatibility wrapper: create the room, then attach the default human leg."""
    create_asterisk_room(caller_channel_id)
    invite_default_human_to_room()


def _apply_owner_side_effects():
    global holder, epoch, current_playback_id, current_assistant_speech_handle
    holder = current_session.owner
    epoch = current_session.epoch  # invalidate any in-flight turn (checked in groq_worker/tts_worker)

    if current_sales_channel_id:
        action = "unmute" if holder == "human" else "mute"
        requests.post(
            f"http://{ARI_HOST}/ari/channels/{current_sales_channel_id}/{action}",
            params={"direction": "in"},
            auth=(ARI_USER, ARI_PASSWORD),
        )

    if holder == "human":
        if current_assistant_speech_handle:
            current_assistant_speech_handle.cancel()
            current_assistant_speech_handle = None
            audio_frame_bridge.mark_ai_interrupted()
            if streaming_output_manager and streaming_output_manager.session:
                try:
                    streaming_output_manager.flush_current()
                except Exception as exc:
                    log(
                        "BARGE_IN",
                        f"streaming flush failed during handoff ({type(exc).__name__}: {exc})",
                    )
        if current_playback_id:
            turn_gate.on_playback_interrupted(current_playback_id)
            ari_delete(f"/playbacks/{current_playback_id}")  # cut AI off mid-sentence
            current_playback_id = None
            current_session.clear_playback()
            audio_frame_bridge.mark_ai_interrupted()

    log("HOLDER", holder)


def set_call_owner(owner, *, reason=None, source="internal"):
    """Switch the product owner of the call while preserving the legacy globals."""
    with _call_control_lock:
        if not current_session.set_owner(owner, reason=reason, source=source):
            return False
        _apply_owner_side_effects()
        return True


def takeover_by_human(*, reason=None, source="internal"):
    return set_call_owner("human", reason=reason, source=source)


def accept_handoff(*, accepted_by=None, source="internal"):
    with _call_control_lock:
        holder_changed = current_session.accept_handoff(accepted_by=accepted_by, source=source)
        if not holder_changed:
            return False
        _apply_owner_side_effects()
        log("HANDOFF", "accepted", payload=current_session.room_debug_payload())
        return True


def resume_ai(*, handback_note=None, resumed_by=None, source="internal"):
    with _call_control_lock:
        holder_changed = current_session.resume_ai(
            handback_note=handback_note,
            resumed_by=resumed_by,
            source=source,
        )
        if not holder_changed:
            return False
        _append_handback_context()
        _apply_owner_side_effects()
        log("HANDOFF", "resumed", payload=current_session.room_debug_payload())
        return True


def _append_handback_context():
    global conversation_history
    conversation_history.append(current_session.handback_context_message())
    if len(conversation_history) > MAX_HISTORY + 1:
        conversation_history = (
            [conversation_history[0]] + conversation_history[-(MAX_HISTORY):]
        )
    current_session.conversation_history = conversation_history


def _handoff_failure_payload(recovery_action):
    payload = current_session.room_debug_payload()
    payload["recovery_action"] = recovery_action
    return payload


def mark_handoff_failure(
    *,
    status,
    reason,
    source="internal",
    channel_id=None,
):
    """Record a human handoff failure and keep the caller in a valid owner state."""
    global current_sales_channel_id
    with _call_control_lock:
        owner_before = current_session.owner
        tracked_channel_id = channel_id or current_sales_channel_id
        current_session.mark_handoff_failure(
            status=status,
            reason=reason,
            source=source,
        )
        if tracked_channel_id:
            ari_delete(f"/channels/{tracked_channel_id}")
            _sales_channel_ids.discard(tracked_channel_id)
            _human_channel_hangup_causes.pop(tracked_channel_id, None)
        if current_sales_channel_id == tracked_channel_id:
            current_sales_channel_id = None

        recovery_action = "ai_remained_owner"
        if owner_before == "human":
            current_session.resume_ai(
                handback_note=f"Human handoff ended unexpectedly: {reason}",
                resumed_by="system",
                source=source,
                reason="handoff_failure_recovery",
            )
            _append_handback_context()
            _apply_owner_side_effects()
            recovery_action = "returned_to_ai"
        else:
            _apply_owner_side_effects()

        log(
            "HANDOFF_FAILURE",
            status,
            payload=_handoff_failure_payload(recovery_action),
        )
        return recovery_action


def _human_failure_status_from_hangup(channel_id):
    hangup = _human_channel_hangup_causes.pop(channel_id, {}) or {}
    cause = hangup.get("cause")
    cause_txt = str(hangup.get("cause_txt") or "").lower()
    if cause == 17 or "busy" in cause_txt:
        return "busy"
    if cause in (21, 603) or "reject" in cause_txt or "declin" in cause_txt:
        return "declined"
    if cause in (18, 19) or "no answer" in cause_txt or "no user response" in cause_txt:
        return "no_answer"
    if current_session.owner == "human" or current_session.handoff_accept_status == "accepted":
        return "dropped"
    if current_session.human_invite_status == "ringing":
        return "no_answer"
    return "dropped"


def toggle_call_owner(*, source="internal"):
    if holder == "ai":
        return accept_handoff(accepted_by=DEFAULT_HUMAN_CALLER_ID, source=source)
    return resume_ai(
        handback_note="manual_toggle",
        resumed_by=DEFAULT_HUMAN_CALLER_ID,
        source=source,
    )


def set_holder(value):
    """Compatibility alias for older scripts/docs that still say holder."""
    return set_call_owner(value, source="legacy_set_holder")


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _send_json(self, body, status=200):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path not in (
            "/internal/handoff/accept",
            "/internal/handoff/resume-ai",
            "/internal/handoff/failure",
        ):
            self._send_json({"error": "not found"}, 404)
            return
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._send_json({"error": "forbidden"}, 403)
            return

        body = self._read_json_body()
        actor = body.get("accepted_by") or body.get("resumed_by") or DEFAULT_HUMAN_CALLER_ID
        try:
            if current_session.status != "active":
                self._send_json(
                    {"error": "no active call", **current_session.room_debug_payload()},
                    409,
                )
                return
            recovery_action = None
            if self.path == "/internal/handoff/accept":
                changed = accept_handoff(accepted_by=actor, source="control_api")
            elif self.path == "/internal/handoff/resume-ai":
                changed = resume_ai(
                    handback_note=body.get("handback_note"),
                    resumed_by=actor,
                    source="control_api",
                )
            else:
                recovery_action = mark_handoff_failure(
                    status=body.get("status") or "failed",
                    reason=body.get("reason") or "handoff failure reported by control API",
                    source="control_api",
                )
                changed = recovery_action == "returned_to_ai"
            response = {
                "ok": True,
                "changed": changed,
                **current_session.room_debug_payload(),
            }
            if recovery_action:
                response["recovery_action"] = recovery_action
            self._send_json(response)
        except RuntimeError as e:
            self._send_json(
                {"error": str(e), **current_session.room_debug_payload()},
                409,
            )
        except ValueError as e:
            self._send_json({"error": str(e)}, 400)


def control_server():
    server = ThreadingHTTPServer((CONTROL_HOST, CONTROL_PORT), ControlHandler)
    log("CONTROL", f"listening on http://{CONTROL_HOST}:{CONTROL_PORT}")
    server.serve_forever()


# --- STEP 3 ADDITION: the container's sounds dir may not exist yet --
# create it once at startup so play_deepgram's docker cp doesn't fail. ---
def ensure_sounds_dir():
    try:
        subprocess.run(
            ["docker", "exec", ASTERISK_CONTAINER, "mkdir", "-p", SOUNDS_DIR_IN_CONTAINER],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        log("SETUP", "Docker CLI was not found. Install Docker Desktop before starting the bridge.")
        raise SystemExit(1)
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip()
        if detail:
            detail = f" Detail: {detail}"
        log(
            "SETUP",
            (
                f"Cannot prepare Asterisk sounds dir in container '{ASTERISK_CONTAINER}'. "
                "Start Docker Desktop and make sure the Asterisk container is running, "
                f"then retry.{detail}"
            ),
        )
        raise SystemExit(1)


def _playback_id_from_event(event):
    playback = event.get("playback") or {}
    return playback.get("id")


def ari_event_loop():
    global current_channel_id, current_company, current_voice, conversation_history
    global current_bridge_id, current_ext_channel_id, current_sales_channel_id
    global current_agent_config
    global holder, epoch, current_playback_id, current_assistant_speech_handle
    global active_streaming_websocket_url

    ws_url = f"ws://{ARI_HOST}/ari/events?api_key={ARI_USER}:{ARI_PASSWORD}&app={APP_NAME}"
    log("ARI", f"connecting to ws://{ARI_HOST}/ari/events?api_key=***:***&app={APP_NAME}")
    ari_ws = create_connection(ws_url)
    log("ARI", f"connected, waiting for calls into {APP_NAME} (Ctrl+C to stop)")

    while True:
        message = ari_ws.recv()
        # --- BUGFIX (2026-07-13): handle each event inside try/except so one
        # bad call (e.g. an ARI 422 while bridging) can't kill the whole loop.
        # Previously an exception here bubbled out of ari_event_loop and the
        # bridge PROCESS EXITED, silently -- then every later call rang into a
        # Stasis app with no handler and dropped on answer. Now the bridge
        # logs the error and stays up for the next call. ---
        try:
            event = json.loads(message)
            event_type = event.get("type")

            if event_type == "StasisStart":
                channel_id = event["channel"]["id"]

                if channel_id in _external_media_channel_ids:
                    # Our own externalMedia channel entering Stasis, not a new
                    # call -- already bridged inside bridge_call_to_external_media().
                    continue
                if channel_id in _streaming_output_channel_ids:
                    # Our own WebSocket output channel entering Stasis, not a
                    # caller. It was already added to the active bridge.
                    continue

                # --- TRANSFER (step 1): our own salesperson leg answered --
                # add to the active bridge, muted. Not a new inbound call. ---
                if channel_id in _sales_channel_ids or channel_id == current_sales_channel_id:
                    ari_post(f"/bridges/{current_bridge_id}/addChannel", channel=channel_id)
                    current_session.set_human_channel(channel_id)
                    requests.post(
                        f"http://{ARI_HOST}/ari/channels/{channel_id}/mute",
                        params={"direction": "in"},
                        auth=(ARI_USER, ARI_PASSWORD),
                    )
                    log("HUMAN_INVITE", "joined", payload=current_session.room_debug_payload())
                    log("SALES", f"joined bridge muted: {channel_id}")
                    continue

                # --- AGENT REGISTRY: resolve the call into a voice-agent config.
                # Today the registry is backed by companies.json; later this is
                # where Customer Registration / Dashboard data plugs in.
                resolution = AGENT_REGISTRY.resolve(
                    stasis_args=event.get("args") or [],
                    dialed_extension=event.get("channel", {}).get("dialplan", {}).get("exten"),
                    default_agent_id=DEFAULT_COMPANY,
                )
                company_key = resolution.agent.company_key
                company = COMPANIES[company_key]
                current_company = company_key
                current_voice = company["voice"]
                current_agent_config = resolution.agent
                conversation_history = [company["system_prompt"]]
                current_session.start_call(
                    caller_channel_id=channel_id,
                    agent=resolution.agent,
                    conversation_history=conversation_history,
                )
                turn_gate.reset_all()
                audio_frame_bridge.reset_gate()
                current_assistant_speech_handle = None
                holder = current_session.owner
                epoch = current_session.epoch
                current_playback_id = current_session.current_playback_id
                runtime_context = _record_runtime_context(source="call_start")

                log("CALL", f"arrived: {channel_id}")
                log("AGENT", company["display_name"])
                if runtime_context:
                    log(
                        "RUNTIME_CONTEXT",
                        "built for active call",
                        payload=_runtime_context_debug_payload(runtime_context),
                    )
                requests.post(
                    f"http://{ARI_HOST}/ari/channels/{channel_id}/answer",
                    auth=(ARI_USER, ARI_PASSWORD),
                )
                bridge_call_to_external_media(channel_id)
                # --- STEP 3 ADDITION: remember the channel so play_deepgram can target it ---
                current_channel_id = channel_id

            elif event_type == "StasisEnd":
                channel_id = event["channel"]["id"]

                if channel_id in _streaming_output_channel_ids:
                    _streaming_output_channel_ids.discard(channel_id)
                    if (
                        streaming_output_manager
                        and streaming_output_manager.session
                        and streaming_output_manager.session.output_channel_id == channel_id
                    ):
                        streaming_output_manager.session = None
                        active_streaming_websocket_url = None
                        current_session.clear_output_stream()
                    continue

                # --- TRANSFER: our own human leg ending should never strand
                # the caller. If human already owned the call, return control
                # to AI; otherwise keep AI as-is and expose the failure.
                if channel_id in _sales_channel_ids:
                    failure_status = _human_failure_status_from_hangup(channel_id)
                    mark_handoff_failure(
                        status=failure_status,
                        reason=f"human channel ended: {channel_id}",
                        source="ari_stasis_end",
                        channel_id=channel_id,
                    )
                    continue

                if channel_id == current_channel_id:
                    log("CALL", f"ended: {channel_id}", blank_before=2)
                    current_channel_id = None
                    stop_streaming_output_route()
                    # --- BUGFIX (2026-07-13): tear down this call's bridge +
                    # externalMedia channel so they don't leak into the Stasis app. ---
                    if current_ext_channel_id:
                        ari_delete(f"/channels/{current_ext_channel_id}")
                    if current_bridge_id:
                        ari_delete(f"/bridges/{current_bridge_id}")
                    # --- TRANSFER (step 1): also hang up + untrack the sales leg. ---
                    if current_sales_channel_id:
                        ari_delete(f"/channels/{current_sales_channel_id}")
                        _sales_channel_ids.discard(current_sales_channel_id)
                        _human_channel_hangup_causes.pop(current_sales_channel_id, None)
                    _external_media_channel_ids.discard(current_ext_channel_id)
                    current_ext_channel_id = None
                    current_bridge_id = None
                    current_sales_channel_id = None
                    current_session.end_call()
                    turn_gate.reset_all()
                    audio_frame_bridge.reset_gate()
                    if current_assistant_speech_handle:
                        current_assistant_speech_handle.cancel()
                    current_assistant_speech_handle = None
                    holder = current_session.owner
                    epoch = current_session.epoch
                    current_playback_id = current_session.current_playback_id

            elif event_type in ("PlaybackFinished", "PlaybackFailed"):
                playback_id = _playback_id_from_event(event)
                if playback_id and playback_id == current_playback_id:
                    if event_type == "PlaybackFinished":
                        turn_gate.on_playback_finished(playback_id)
                        audio_frame_bridge.mark_ai_done_speaking()
                    else:
                        turn_gate.on_playback_interrupted(playback_id)
                        audio_frame_bridge.mark_ai_interrupted()
                    current_session.clear_playback()
                    current_playback_id = current_session.current_playback_id
                    if current_assistant_speech_handle:
                        current_assistant_speech_handle.cancel()
                    current_assistant_speech_handle = None
                    log("PLAYBACK", event_type, payload={"playback_id": playback_id})

            elif event_type == "ChannelHangupRequest":
                channel_id = event.get("channel", {}).get("id")
                if channel_id in _sales_channel_ids or channel_id == current_sales_channel_id:
                    _human_channel_hangup_causes[channel_id] = {
                        "cause": event.get("cause"),
                        "cause_txt": event.get("cause_txt"),
                    }

            # --- TRANSFER (step 2): DTMF-triggered owner toggle. The salesperson
            # presses `1` on their softphone to take the call over or hand it back.
            # This now goes through the same product-level call-control functions
            # that a dashboard/API endpoint can call in a later increment. ---
            elif event_type == "ChannelDtmfReceived":
                digit = event.get("digit")
                ch = event.get("channel", {}).get("id")
                log("DTMF", f"{digit} from {ch}")
                if ch == current_sales_channel_id and digit == "1":
                    toggle_call_owner(source="dtmf")

        except Exception as e:
            log("ARI", f"error handling event ({type(e).__name__}: {e}); call skipped, bridge still up")


# --- STEP 3 ADDITION: make sure the container has somewhere to receive played-back files ---
ensure_sounds_dir()

# begin concurrent threads
# --- STEP 2 CHANGE: added rtp_listener + ari_event_loop; removed the old
# mic-based deepgram_worker (agent-test6.py had already moved STT to
# modulate_worker, so deepgram is TTS-only here, called directly from
# tts_worker). ---
threads = [
    threading.Thread(target=control_server, daemon=True),
    threading.Thread(target=rtp_listener, daemon=True),
    threading.Thread(target=modulate_worker, daemon=True),
    threading.Thread(target=turn_gate_worker, daemon=True),
    threading.Thread(target=groq_worker, daemon=True),
    threading.Thread(target=tts_worker, daemon=True),
]

for t in threads:
    t.start()

try:
    ari_event_loop()
except KeyboardInterrupt:
    print("\nShutting down...")
