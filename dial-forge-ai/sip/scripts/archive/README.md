# Archived SIP Bridge Experiments

These files are older bridge or transport experiments kept for reference only.
Do not use them for the current LiveKit migration path.

Use the LiveKit migration modules instead:

```bash
venv/bin/python -m unittest livekit_runtime.tests.test_telephony
```

Archived files:

- `step2_stt_bridge.py` - earlier STT/LLM/TTS bridge before AI-human-AI handoff work.
- `asterisk_legacy/` - final Asterisk bridge/runtime code before Phase 5 telephony migration.
- `archive-pipecat-frame/poc_chan_websocket_echo.py` - chan_websocket proof of concept.
- `archive-pipecat-frame/poc_pipecat_agent_transport.py` - Pipecat agent transport proof of concept.
- `archive-pipecat-frame/poc_pipecat_transport.py` - Pipecat transport proof of concept.
