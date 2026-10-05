# Repository Structure

Created: 2026-10-04

DealPilot is moving from an internship-shaped workspace into an agent-first
open-source project. The repo intentionally uses direct top-level folders
instead of `apps/` and `packages/` so the architecture is easy to scan.

```text
deal-pilot/
├── ui/                         # Product UI
├── api/                        # HTTP API boundary
├── agent-worker/               # Runtime worker entrypoints
├── agent-core/                 # Agent profile, policy, capability runtime
├── voice-runtime/              # LiveKit, SIP, Asterisk, voice adapters
├── conversation-pipeline/      # Future turn pipeline boundary
├── knowledge/                  # RAG, ingestion, retrieval
├── capabilities/               # Product action/tool modules
├── integrations/               # CRM/provider connectors
├── sessions/                   # AgentSession and call-session state
├── observability/              # Metrics, traces, replay, debugging
├── data-model/                 # Supabase schema/types/config
├── evals/                      # Prompt, retrieval, and call-quality evals
├── examples/                   # Sample agents and knowledge bases
├── deploy/                     # Deployment assets
├── docs/                       # Architecture and reference docs
└── archive/                    # Archived legacy surfaces
```

## Current Compatibility Boundary

The Python modules keep their existing import package names for now:

```text
agent-core/runtime       -> import runtime
knowledge/rag            -> import rag
sessions/communication   -> import communication
voice-runtime/livekit_runtime -> import livekit_runtime
```

Run Python commands from the repo root with:

```bash
export PYTHONPATH=agent-core:knowledge:sessions:voice-runtime
```

This lets the codebase move into the new architecture without rewriting every
import in the same step.
