# Airborne Admissions ADK Agent

Standalone Google ADK agent, deployed separately from the main Cloud Run
service, hosting only the conversational-reasoning turn (persona + RAG tool)
described in the top-level plan for moving off "plain Cloud Run" onto the
Gemini Enterprise Agent Platform / Vertex AI Agent Engine.

Telephony call control, STT/TTS, guardrails, DB, CRM sync, and WhatsApp
automation all stay on Cloud Run (repo root) — this package is intentionally
minimal and has no dependency on FastAPI/Twilio/psycopg2/etc.

## Before deploying: unverified facts to confirm

The following could not be verified when this was written (the relevant
Google docs were unreachable from the dev environment):

1. Exact ADK pip package name (`agent/requirements.txt` currently guesses
   `google-adk` — confirm).
2. `agents-cli` command syntax for `init`/`run`/`deploy`, and the exact
   symbol name (assumed `root_agent` in `agent.py`) the deploy tooling
   expects the agent module to expose.
3. The deployed Agent Engine's query API shape (`agent_client.py` on the
   Cloud Run side assumes `engine.query(input=..., history=..., user_id=...)`
   returning either a plain string or a dict with `output`/`text`/
   `content.parts` — confirm against the real SDK).
4. Whether ADK's `LlmAgent` exposes a `thinking_budget`/`thinking_config`
   equivalent to the raw Gemini REST payload's
   `generationConfig.thinkingConfig.thinkingBudget: 0`, used today in the
   Cloud Run side's `gpt_test.py` for phone-call latency
   (`.agents/rules/voice-telephony-llm.md`). If unsupported, this is a
   go/no-go blocker, not a detail to skip — see the latency head-to-head
   step below.
5. Agent Engine's supported regions vs. the project's existing
   `asia-south1` Cloud Run/Cloud SQL region.

Do not trust `agent.py`, `deploy_agent.sh`, or `agent_client.py` (Cloud Run
side, repo root) as verified-working code until these are confirmed and the
verification steps below pass.

## Local dev loop

```bash
cd agent
pip install -r requirements.txt
cp .env.example .env   # fill in GCP_PROJECT, GCP_LOCATION, RAG_ENDPOINT_URL, etc.
# Confirm the real local-dev command against ADK/agents-cli docs, e.g.:
# agents run .
```

Converse with the agent and check: persona/tone matches the instruction in
`prompts.py`, `search_knowledge` fires for aviation-keyword questions and
is skipped for filler turns, `[EXIT]` appears on call-ending turns,
responses stay to 2-3 short sentences, and English/Hinglish mirroring works.

## Deploy

```bash
./deploy_agent.sh
```

This is a placeholder (see the script's own comments) until the exact
`agents-cli`/Agent Engine SDK deploy command is confirmed. On success it
should print the deployed agent's resource name — set that as
`AGENT_ENGINE_RESOURCE_NAME` on the Cloud Run service (repo root
`deploy.sh`/`deploy.ps1`) before enabling `USE_AGENT_ENGINE=true`.

## Verification before cutover

1. Local dev loop (above).
2. RAG wiring: confirm `rag_client.py` round-trips through Cloud Run's
   `/internal/rag/query` endpoint, and falls back to `knowledge_base.py`'s
   static search if that call fails.
3. Scripted smoke test: `python -m agent.tests.test_agent_local` from the
   repo root, against the deployed agent.
4. **Latency head-to-head** (critical gate): compare wall-clock latency of
   this path vs. the existing direct-Gemini path in `gpt_test.py` on
   identical prompts. Do not cut over if `thinking_budget=0` isn't
   reproducible here and latency regresses meaningfully — this backs a live
   phone line.
5. Real test call via the `AGENT_ENGINE_ROLLOUT_PHONES` allowlist
   (`config.py`, repo root) before flipping `USE_AGENT_ENGINE=true` globally.
