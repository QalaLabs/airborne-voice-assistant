"""
ADK Agent definition for Airborne Aviation Academy's admissions/conversation
core, deployed to Vertex AI Agent Engine.

VERIFICATION NEEDED before this can be trusted to run (see the plan's
"Unverified facts" section -- ADK/agents-cli docs were unreachable from the
dev environment this was written in):
  1. Exact ADK package name and import path for the Agent/LlmAgent class
     (assumed here: `google.adk.agents.LlmAgent`, matching ADK's public
     samples as of its initial releases -- confirm against the installed
     package's actual API before deploying).
  2. The symbol name `agents-cli deploy` / Agent Engine's SDK-based deploy
     expect this module to expose (assumed here: `root_agent`, matching
     current ADK sample conventions -- confirm and rename if different).
  3. Whether ADK's model config exposes a `thinking_budget`/`thinking_config`
     equivalent to the raw Gemini REST payload's
     `generationConfig.thinkingConfig.thinkingBudget: 0` used in the
     existing gpt_test.py (see .agents/rules/voice-telephony-llm.md -- this
     is a hard latency requirement for phone calls). If ADK does not expose
     this, treat it as a go/no-go blocker per the plan's latency
     head-to-head verification step, not something to silently skip.
  4. Confirm the model id string format ADK/Agent Engine expects (may not be
     identical to the raw Generative Language API model names used in
     gpt_test.py, e.g. "gemini-3.8-flash").

Do not deploy this without first running it through `agents run`
(or ADK's local dev-loop equivalent) and the smoke test in
agent/tests/test_agent_local.py.
"""

import os

from prompts import AGENT_INSTRUCTION
from tools import search_knowledge

# NOTE: import path/class name unverified -- see module docstring, item 1.
from google.adk.agents import LlmAgent

MODEL_ID = os.environ.get("AGENT_MODEL_ID", "gemini-flash-latest")

# NOTE: symbol name `root_agent` unverified -- see module docstring, item 2.
root_agent = LlmAgent(
    name="airborne_admissions_agent",
    model=MODEL_ID,
    instruction=AGENT_INSTRUCTION,
    tools=[search_knowledge],
    # NOTE: thinking-budget passthrough unverified -- see module docstring,
    # item 3. If LlmAgent doesn't accept a `generate_content_config`-style
    # kwarg for this, that needs a different mechanism (or is unsupported).
    # generate_content_config={"thinking_config": {"thinking_budget": 0}},
)
