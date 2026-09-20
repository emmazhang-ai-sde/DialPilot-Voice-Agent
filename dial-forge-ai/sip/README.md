# SIP Voice Agent

A phone-call AI agent: a caller talks to a company's AI over SIP.

Design docs: [`design-docs-sip/`](design-docs-sip/). This README is just how to run it.

```
Softphone / product frontend  <->  Asterisk (Docker)  <->  stt_bridge_ai_human_transfer.py
                                                            (STT -> LLM -> TTS + handoff)
```

## Folders

| Path | What |
|---|---|
| `scripts/stt_bridge_ai_human_transfer.py` | Live bridge: call audio -> Modulate STT -> Groq LLM -> Deepgram Aura TTS -> back into the call, with AI-human-AI handoff |
| `scripts/` | Current SIP runtime entrypoints |
| `scripts/archive/` | Older bridge and transport experiments kept for reference only |
| `../knowledge-base/` | Per-company KB + `companies.json` (extension, voice, KB file) |

## Prerequisites

- Docker running, and the `asterisk-mvp` container (see the Step 1 doc if it does not exist yet).
- Python deps in the repo venv. **Always use `venv/bin/python`** - the system `python3` does not have them.
- A softphone (Linphone) registered to `test-endpoint` (Step 1 doc).
- API keys in `ai-pipeline/.env.local` (Deepgram, Groq, Modulate; Supabase is optional).

## Run it - two terminals, all from `globifye-ai/`

```bash
# 1. Asterisk (the SIP server). Container already exists -> start it:
docker start asterisk-mvp
#    First time only, if the container does not exist:
#    docker run -d --name asterisk-mvp \
#      -p 5060:5060/udp -p 8088:8088/tcp -p 10000-10100:10000-10100/udp \
#      -v $(pwd)/asterisk-config:/etc/asterisk andrius/asterisk

# 2. The live bridge (STT -> LLM -> TTS). Must be the venv Python, with -u:
venv/bin/python -u sip/scripts/stt_bridge_ai_human_transfer.py
```

## Runtime debug API

The bridge also exposes a localhost-only control/debug server on port `8500`.

```bash
# Current active session, including owner, room ids, handoff state, report context, and legacy mirror globals.
curl http://127.0.0.1:8500/internal/runtime/session

# Runtime timeline for all managed events.
curl http://127.0.0.1:8500/internal/runtime/timeline

# Incremental timeline polling after a known sequence number.
curl "http://127.0.0.1:8500/internal/runtime/timeline?since_sequence=20"

# Timeline for one call session id.
curl "http://127.0.0.1:8500/internal/runtime/timeline?call_session_id=<call-session-id>"
```

## The call (softphone routing)

Place the call from the product frontend or dial directly from Linphone. The number reaches the matching business, whose AI sales rep answers grounded in that company's knowledge base and works the prospect through a five-stage pipeline (Prospect -> Contact -> Demo -> Proposal -> Closing):

| Dial | Business | Sells | Voice |
|---|---|---|---|
| `1000` | Pacific Beef Trading | USDA beef export (B2B) | `aura-2-thalia-en` |
| `2000` | GlobiFYE | AI voice agents — product: DialForge (B2B) | `aura-2-arcas-en` |

Answer the softphone when it rings. Talk, then hang up.

## Quick checks

```bash
# Is Asterisk up and the bridge registered to it?
docker exec asterisk-mvp asterisk -rx "ari show apps"      # lists sip-mvp-app
docker exec asterisk-mvp asterisk -rx "dialplan show sip-mvp"   # shows 1000 + 2000
```

If a call rings but drops the instant you answer, the bridge (terminal 2) is not running - it must be started with `venv/bin/python`, not system `python3`.
