# GlobiFYE — AI Team

This repository contains the work of the GlobiFYE AI subteam.

## Repository Structure

- **`ai-pipeline/`** — AI pipeline development and related code
- **`sip/`** — SIP voice-agent work: bridge scripts, archived experiments, knowledge base
- **`design-docs/`** — tech decision documentation and files coordinated with other teams
- **`[member-name]/`** — Individual folders for each AI team member's personal notes and working files

## How to run the frontends

There are two frontend/reference areas in this repo. Each has its own README with full setup, environment variables, and troubleshooting; the quick-start commands are:

| Frontend | Start command (from repo root) | URL | Details |
|----------|-------------------------------|-----|---------|
| AI pipeline web UI | `cd ai-pipeline && npm run dev` | http://localhost:3400 | [ai-pipeline/README.md](ai-pipeline/README.md) |
| Frontend team references | none, open the `.html` files directly in a browser | n/a | [design-docs/frontend-sync/README.md](design-docs/frontend-sync/README.md) |

Notes:

- The pipeline UI reads secrets from `ai-pipeline/.env.local` (not committed). See its README for the variable list.
- A full live-call check still needs Asterisk, a registered softphone, and the bridge script running. See [sip/README.md](sip/README.md).
