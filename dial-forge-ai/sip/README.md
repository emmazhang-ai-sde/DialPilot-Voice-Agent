# Telephony Voice Agent

A phone-call AI agent: a caller talks to a company's AI over LiveKit voice
runtime paths.

Design docs: [`design-docs-sip/`](design-docs-sip/). This README is just how to run it.

```
local-room:
Browser / LiveKit Meet  <->  local LiveKit room  <->  DialForge Agent worker

local-sip:
Linphone  <->  livekit-sip  <->  local LiveKit room  <->  DialForge Agent worker
```

## Folders

| Path | What |
|---|---|
| `../livekit_runtime/telephony.py` | Current Phase 5 telephony profiles and LiveKit handoff adapter |
| `../livekit_runtime/local_voice_agent.py` | Shared LiveKit Agent worker used by both local-room and local-sip |
| `../livekit_runtime/local_room.py` | Browser / LiveKit Meet entrypoint wrapper |
| `../livekit_runtime/local_sip.py` | Linphone / livekit-sip entrypoint wrapper |
| `livekit-sip.config.example.yaml` | Local self-hosted `livekit-sip` config sample |
| `scripts/tests/` | Tests for archived voice runtime helpers |
| `scripts/archive/asterisk_legacy/` | Archived Asterisk bridge implementation kept for reference only |
| `scripts/archive/` | Older bridge and transport experiments kept for reference only |
| `../knowledge-base/` | Per-company KB + `companies.json` (extension, voice, KB file) |

## Prerequisites

- Python deps in the repo venv. **Always use `venv/bin/python`** - the system `python3` does not have them.
- A local LiveKit server for `local-room`.
- `livekit-sip`, Redis, and a direct SIP client such as Linphone for `local-sip`.
- API keys for the selected STT, LLM, and TTS providers.

## Local Room Profile

```bash
livekit-server --dev
lk token create --api-key devkey --api-secret secret \
  --join --room dialforge-globifye-local-room --identity local-caller --valid-for 24h
```

Open LiveKit Meet with the generated token and join the same room as the local
agent worker. This is the default human test path for AI-handled calls because
it verifies STT, TTS, RAG, tools, workflow, and handoff decisions without SIP
setup.

Run the local worker in another terminal:

```bash
LIVEKIT_URL=ws://localhost:7880 \
LIVEKIT_API_KEY=devkey \
LIVEKIT_API_SECRET=secret \
DIALFORGE_COMPANY_KEY=globifye \
venv/bin/python -m livekit_runtime.local_room dev
```

## Local SIP Profile

```bash
livekit-server --dev
redis-server
livekit-sip --config=sip/livekit-sip.config.example.yaml
LIVEKIT_URL=ws://localhost:7880 \
LIVEKIT_API_KEY=devkey \
LIVEKIT_API_SECRET=secret \
DIALFORGE_COMPANY_KEY=globifye \
venv/bin/python -m livekit_runtime.local_sip dev
```

Then place a direct SIP call from Linphone to the configured local SIP URI, for
example `sip:127.0.0.1:5060` if your network setup supports it. Use this path
when validating SIP participant metadata, DTMF, hangup, warm transfer, and call
lifecycle events.

For human handoff/warm transfer tests, configure:

```bash
LIVEKIT_SIP_OUTBOUND_TRUNK=ST_xxx
LIVEKIT_SUPERVISOR_PHONE_NUMBER=+15550002222
LIVEKIT_SIP_NUMBER=+15550001111
```

## Business Routing

The previous Asterisk dialplan used these local extensions. Keep them as
reference when mapping LiveKit dispatch rules or room metadata:

| Legacy Dial | Business | Sells | Voice |
|---|---|---|---|
| `1000` | Pacific Beef Trading | USDA beef export (B2B) | `aura-2-thalia-en` |
| `2000` | GlobiFYE | AI voice agents — product: DialForge (B2B) | `aura-2-arcas-en` |

## Archived Asterisk Path

The previous Asterisk bridge is archived at
`scripts/archive/asterisk_legacy/stt_bridge_ai_human_transfer.py`.

Do not build new features against the archived bridge. Use it only as a
reference for behavior that needs to be reimplemented through LiveKit room/SIP
participants.
