# Asterisk Legacy Bridge

This folder contains the pre-Phase-5 Asterisk voice bridge implementation.

It is archived for reference while DialForge migrates telephony to LiveKit:

```text
Old:
Linphone -> Asterisk/PJSIP -> stt_bridge_ai_human_transfer.py

New local-room:
Browser / LiveKit Meet -> LiveKit room -> DialForge Agent worker

New local-sip:
Linphone -> livekit-sip -> LiveKit room -> DialForge Agent worker
```

Do not add new agent/tool/runtime features here. Use `livekit_runtime/` for new
work and refer back to this folder only when preserving behavior from the old
bridge.

Main archived entrypoint:

```bash
venv/bin/python -u sip/scripts/archive/asterisk_legacy/stt_bridge_ai_human_transfer.py
```
