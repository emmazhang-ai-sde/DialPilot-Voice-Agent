# LiveKit Runtime Prototype

Phase 1 goal: validate the LiveKit-style agent/tool interface without changing
the original Asterisk media path.

This package wraps the existing DialForge RuntimeCapability layer as
LiveKit-shaped tools:

```text
RuntimeCapability
  -> @function_tool

RuntimeContext
  -> DialForgeSessionState on AgentSession.userdata

execute_capability_call()
  -> tool implementation body

CRM MCP
  -> provider-agnostic CRMMCPConfig
  -> MCPToolset attached to AgentSession(tools=...)
```

## Scope Split

Session-scoped tools:

```text
retrieve_company_kb
request_handoff
CRM MCP toolset
```

Agent-scoped tools:

```text
stage transition tools generated from RuntimeContext.stage_transitions
```

This mirrors LiveKit's lifecycle: session tools survive handoff, while agent
tools change with the active stage agent.

## Provider-Agnostic CRM MCP

DialForge uses stable CRM action names first:

```text
search_contact
get_contact
search_company
create_contact
update_contact
add_note
log_call
create_followup_task
```

Each CRM provider can map those actions to its actual MCP tool names:

```python
from livekit_runtime.tools import CRMMCPConfig


crm_config = CRMMCPConfig(
    provider="salesforce",
    url="https://salesforce.example.com/mcp",
    allowed_actions=("search_contact", "create_contact", "log_call"),
    action_tool_map={
        "search_contact": "salesforce_search_contact",
        "create_contact": "salesforce_create_lead",
        "log_call": "salesforce_log_activity",
    },
)
```

This keeps the agent/runtime contract stable when switching from HubSpot to
Salesforce, Zoho, or an internal CRM MCP server.

## Usage Shape

```python
from livekit_runtime.prototype_agent import build_prototype_session_and_agent
from livekit_runtime.tools import DialForgeToolHandlers

session, agent = build_prototype_session_and_agent(
    runtime_context,
    handlers=DialForgeToolHandlers(
        retrieval_handler=retrieve_from_kb,
        stage_transition_handler=transition_stage,
        human_handoff_handler=request_human,
    ),
)
```

This only builds LiveKit-style objects. It does not connect to a LiveKit room
or replace the SIP bridge.

## Phase 2 Turn Runner

`turn_runner.py` moves the OpenAI/Groq-compatible streaming tool loop out of
`sip/scripts/stt_bridge_ai_human_transfer.py`.

The bridge now delegates one assistant turn to:

```python
RuntimeCapabilityTurnRunner(...).run(
    conversation_history,
    on_first_token=...,
    on_sentence=...,
    should_continue=...,
)
```

The runner owns:

```text
streaming model call
tool_call delta assembly
assistant/tool message insertion
per-turn call budget
LiveKit-style function tool execution
tool-round retry / fallback response
```

The SIP bridge still owns:

```text
transcript queue
call owner checks
epoch / barge-in suppression
TTS enqueue
conversation trimming
```

This is still compatible with the current Groq chat-completions client. The
next step is to swap the runner implementation to a real `AgentSession.run`
path once `livekit-agents` and the chosen LLM plugin are installed in the
runtime environment.

## Phase 4 Workflow / Handoff Agents

`workflow.py` adds a media-free stage-agent layer:

```text
WorkflowDefinition
  -> WorkflowStage[]
  -> DialForgeWorkflowAgent per active stage
  -> stage transition tools that return the next Agent
```

Example:

```python
from livekit_runtime.workflow import WorkflowDefinition, WorkflowStage
from runtime.vocabulary import StageTransition


workflow = WorkflowDefinition(
    initial_stage="prospect",
    stages={
        "prospect": WorkflowStage(
            name="prospect",
            instructions="Qualify whether there is a phone workflow.",
            transitions=(
                StageTransition(
                    name="confirmed_worth_automating",
                    target="contact",
                    description="Caller confirmed a meaningful phone workflow.",
                ),
            ),
        ),
        "contact": WorkflowStage(
            name="contact",
            instructions="Collect and confirm contact details.",
        ),
    },
)
```

The handoff tool updates `AgentSession.userdata.stage`, records the transition,
optionally calls the existing stage transition handler, and returns a new
`DialForgeWorkflowAgent` for the target stage. In real LiveKit, returning the
agent is the handoff primitive.

## Phase 5 Telephony Migration

`telephony.py` makes the migrated local test surface explicit, and
`local_voice_agent.py` is the shared LiveKit worker for both paths:

```text
local-room
  Browser / LiveKit Meet
  -> local LiveKit room
  -> DialForge Agent worker
  -> Browser audio response

local-sip
  Linphone direct SIP call
  -> livekit-sip
  -> local LiveKit room
  -> DialForge Agent worker
  -> livekit-sip
  -> Linphone audio response
```

Use `local-room` for daily human testing of the AI-handled call experience:
STT, TTS, RAG, function tools, workflow, and handoff decisions. It bypasses SIP
so iteration is fast.

The default local media path uses direct provider plugins rather than LiveKit
Cloud inference, because local `devkey`/`secret` credentials only authenticate
the local room server:

```bash
DIALFORGE_MEDIA_PROVIDER=direct
DIALFORGE_STT_PROVIDER=deepgram
DIALFORGE_STT_MODEL=nova-3
DIALFORGE_STT_LANGUAGE=en-US
DIALFORGE_LLM_PROVIDER=groq
DIALFORGE_LLM_MODEL=openai/gpt-oss-120b
DIALFORGE_TTS_PROVIDER=deepgram
DIALFORGE_TTS_MODEL=aura-2-arcas-en
```

Run it locally:

```bash
# terminal 1
livekit-server --dev

# terminal 2
LIVEKIT_URL=ws://localhost:7880 \
LIVEKIT_API_KEY=devkey \
LIVEKIT_API_SECRET=secret \
DIALFORGE_COMPANY_KEY=globifye \
.venv/bin/python -m livekit_runtime.local_room dev

# terminal 3: generate a browser token and open LiveKit Meet
lk token create \
  --api-key devkey --api-secret secret \
  --join --room dialforge-globifye-local-room \
  --identity local-caller --valid-for 24h
```

Use `local-sip` for integration testing of telephony behavior: SIP participant
metadata, DTMF, hangup, warm transfer, and call lifecycle events. It keeps
Linphone as the caller, but it targets LiveKit SIP instead of Asterisk.

Run it locally:

```bash
# terminal 1
livekit-server --dev

# terminal 2
redis-server

# terminal 3
livekit-sip --config=sip/livekit-sip.config.example.yaml

# terminal 4
LIVEKIT_URL=ws://localhost:7880 \
LIVEKIT_API_KEY=devkey \
LIVEKIT_API_SECRET=secret \
DIALFORGE_COMPANY_KEY=globifye \
.venv/bin/python -m livekit_runtime.local_sip dev
```

Then place a direct SIP call from Linphone to the URI exposed by the local
`livekit-sip` process. For warm transfer/human handoff testing, set:

```bash
LIVEKIT_SIP_OUTBOUND_TRUNK=ST_xxx
LIVEKIT_SUPERVISOR_PHONE_NUMBER=+15550002222
LIVEKIT_SIP_NUMBER=+15550001111
```

The Asterisk implementation is now legacy reference material under
`sip/scripts/archive/asterisk_legacy/`. The migration target is:

```text
LiveKit room
  + LiveKit SIP participant for phone callers
  + browser participant for local-room callers
  + AgentSession tools and workflow agents
```

Human handoff now has a provider-neutral shape:

```python
from livekit_runtime.telephony import LiveKitSIPConfig, LiveKitTelephonyAdapter
from livekit_runtime.tools import DialForgeToolHandlers


telephony = LiveKitTelephonyAdapter(
    LiveKitSIPConfig(
        sip_trunk_id="ST_xxx",
        sip_number="+15550001111",
        default_human_endpoint="+15550002222",
    )
)

handlers = DialForgeToolHandlers(
    human_handoff_handler=telephony.handoff_handler(),
)
```

The handler currently builds the same kwargs expected by LiveKit's warm-transfer
task shape without importing beta telephony classes at module import time. When
the real `AgentSession` worker is connected, this is the adapter that should
instantiate and run the LiveKit warm transfer.

## Tests

```bash
.venv/bin/python -m unittest livekit_runtime.tests.test_tools
.venv/bin/python -m unittest livekit_runtime.tests.test_turn_runner
.venv/bin/python -m unittest livekit_runtime.tests.test_workflow
.venv/bin/python -m unittest livekit_runtime.tests.test_telephony
.venv/bin/python -m unittest livekit_runtime.tests.test_local_config
```
