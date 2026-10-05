# DealPilot Voice Agent

DealPilot is a continuation of my internship work on sales voice agents. The
project moves that prototype forward into a portfolio-ready system for
AI-assisted outbound calling, company-specific knowledge retrieval, live call
workflow control, and post-call analysis.

The repository still contains some `dial-forge-*` paths because the codebase
started as an internship voice-agent workspace. The current direction is
DealPilot: a sales voice-agent platform that can answer from a business
knowledge base, run structured call stages, support human handoff, and connect
call outcomes back to product data.

## What It Does

- Runs a voice-agent runtime for sales calls and local telephony experiments.
- Retrieves company-specific answers from a RAG knowledge base.
- Models call stages, tool permissions, and handoff behavior explicitly.
- Supports local product UI flows such as login, active call, power dialer,
  contacts, call history, post-call summary, knowledge, integrations, and
  settings.
- Stores product, call, transcript, analysis, and billing data in Supabase.
- Keeps older Asterisk/SIP bridge work as reference while moving toward
  LiveKit-style local room and SIP runtimes.

## Tech Stack

| Area | Stack |
| --- | --- |
| Voice runtime | Python, LiveKit Agents, SIP/local room experiments |
| AI pipeline | Groq/OpenAI-compatible chat loop, tool calls, runtime capabilities |
| Speech | Deepgram STT, edge-tts/TTS experiments |
| RAG | Haystack, Qdrant, Supabase pgvector fallback |
| Document parsing | Azure Document Intelligence, Docling-style fallback paths |
| Backend data | Supabase Postgres, Auth, REST, pgvector |
| Frontend | Static HTML/CSS/JS product screens, local Python dev server |
| Telephony reference | LiveKit SIP, archived Asterisk bridge configuration |
| Testing | Python `unittest` tests across runtime, RAG, SIP, and call-session modules |

## Repository Structure

```text
deal-pilot/
├── ui/
│   └── console/                # Static product console and local UI server
├── api/                        # Future HTTP API boundary for UI and SDK access
├── agent-worker/               # Future runtime worker entrypoint for sessions
├── agent-core/
│   └── runtime/                # Capability registry, policy, execution, context
├── voice-runtime/
│   ├── livekit_runtime/        # Local room, local SIP, workflow, and tool adapters
│   ├── sip/                    # Telephony runbooks and archived bridge references
│   ├── voice/                  # Voice runtime package placeholder
│   └── asterisk-config/        # Legacy Asterisk configuration reference
├── knowledge/
│   └── rag/                    # Knowledge ingestion, retrieval, and provider config
├── sessions/
│   └── communication/          # Call session and handoff state primitives
├── data-model/
│   └── config/                 # Shared config/data-model package placeholder
├── examples/
│   ├── agents/                 # Historical teammate/agent experiments
│   └── knowledge-bases/        # Example company profiles and documents
├── docs/
│   ├── architecture/           # Architecture notes and migration plans
│   └── reference/              # Preserved internship/reference documents
├── capabilities/               # Future product capability modules
├── integrations/               # Future CRM/provider integration modules
├── observability/              # Future metrics, traces, replay, and debugging
├── evals/                      # Future prompt, retrieval, and call-quality evals
├── deploy/                     # Future Docker/env/deployment assets
└── archive/                    # Archived product surfaces and legacy references
```

## Key Concepts

### Runtime Capabilities

The agent does not receive arbitrary backend access. The runtime builds a
scoped context for the current call and exposes only the capabilities allowed
for the active company, agent, workflow stage, and handoff state.

### Company Knowledge

Company documents live under `examples/knowledge-bases/`. The RAG layer can
ingest and retrieve chunks through the active provider stack, with newer
Haystack/Qdrant code and archived Supabase pgvector scripts kept for reference.

### Voice Runtime

The project keeps two runtime paths visible:

- `local-room`: fast local validation through a LiveKit room.
- `local-sip`: SIP-oriented validation for caller metadata, lifecycle events,
  DTMF, hangup, and warm transfer behavior.

The older Asterisk bridge is archived as behavioral reference, not the primary
path for new work.

### Product Console

The frontend is a static product console prototype under `ui/console`, with
active screens for login, active call, power dialer, contacts, call history,
post-call summary, knowledge configuration, integrations, and settings. The
local server adds lightweight API endpoints for auth, user hydration, call
queue access, knowledge uploads, and SIP demo proxying.

## Quick Start

### Backend Setup

```bash
cd /Users/shuyangzhang/20-voice-agent/deal-pilot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create a local `.env.local` as needed for providers such as Supabase, LiveKit,
Deepgram, Groq/OpenAI-compatible models, Qdrant, and Azure Document
Intelligence. Do not commit secrets.

### Run Tests

```bash
cd /Users/shuyangzhang/20-voice-agent/deal-pilot
export PYTHONPATH=agent-core:knowledge:sessions:voice-runtime
.venv/bin/python -m unittest discover agent-core sessions knowledge voice-runtime
```

For narrower checks:

```bash
.venv/bin/python -m unittest discover -s agent-core/runtime -p 'test_*.py'
.venv/bin/python -m unittest discover -s knowledge/rag/tests -p 'test_*.py'
.venv/bin/python -m unittest discover -s voice-runtime/livekit_runtime/tests -p 'test_*.py'
```

### Run The Product UI

```bash
cd /Users/shuyangzhang/20-voice-agent/deal-pilot/ui/console
python3 localHost/dial_forge_front_end_server.py
```

Open:

```text
http://localhost:8000/login.html
```

The local server can use Supabase Auth when configured. If Supabase is not
available, it can fall back to local demo users in `localHost/`.

### Run A Local LiveKit Room Agent

```bash
cd /Users/shuyangzhang/20-voice-agent/deal-pilot
export PYTHONPATH=agent-core:knowledge:sessions:voice-runtime

LIVEKIT_URL=ws://localhost:7880 \
LIVEKIT_API_KEY=devkey \
LIVEKIT_API_SECRET=secret \
DIALFORGE_COMPANY_KEY=globifye \
.venv/bin/python -m livekit_runtime.local_room dev
```

See [voice-runtime/livekit_runtime/README.md](voice-runtime/livekit_runtime/README.md)
and [voice-runtime/sip/README.md](voice-runtime/sip/README.md) for the full
local room and SIP setup.

## Supabase Data Model

The current database model includes:

- product identity: `organizations`, `users`, `contacts`, `agent_configs`
- dialer workflow: `call_queue`, `call_queue_events`
- call records: `recordings`, `transcript`, `analysis`, `topics`, `sip_calls`
- RAG: `sip_kb_chunks`, `match_kb_chunks`
- product operations: `api_keys`, `crm_integrations`, `subscriptions`,
  `transactions`, `payment_logs`, `phone_numbers`, `webhooks`

Post-call summaries and coaching analysis are stored through the `analysis`
table, linked to `recordings` and `transcript`.

## Project Status

This is an active portfolio project. The repo contains a mix of working
runtime modules, tested service boundaries, static product prototypes, and
archived experiments from the original internship workspace.

Current focus:

- make DealPilot the primary product identity across the codebase
- connect the product console to the active Supabase project
- harden the LiveKit local room and SIP runtime paths
- keep RAG ingestion/retrieval provider-agnostic
- turn post-call analysis and handoff events into first-class product workflows

## Notes

- The codebase intentionally preserves some historical context from the
  internship prototype.
- Secrets should stay in local `.env.local` files or provider dashboards.
- Archived bridge code is kept for reference and should not be used as the
  foundation for new runtime work.
