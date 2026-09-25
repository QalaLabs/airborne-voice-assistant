"""
Thin client for querying the deployed ADK conversational agent on Vertex AI
Agent Engine, used by assistant.py's handle_conversation() when
config.USE_AGENT_ENGINE (or the per-phone rollout allowlist) is active.

Preserves the same call contract as gpt_test.chat_with_gpt() from the
caller's point of view: takes the current turn + pruned history, returns
plain response text. All response post-processing (₹->Rs. normalization,
[EXIT] detection/stripping) stays the caller's (assistant.py's)
responsibility, unchanged, so this module only needs to return raw text.

VERIFICATION NEEDED (see plan's "Unverified facts" section — the ADK/Agent
Engine docs were unreachable from this environment when this was written):
  - Exact query API shape: whether `.query()` accepts a plain string,
    a `input=` kwarg, or a structured request/session object, and whether
    it returns a string, a dict, or an event/content object with candidate
    parts that need concatenating (mirroring gpt_test.chat_with_gemini's
    `''.join(p.get('text','') for p in parts)` discipline).
  - Exact import path for the client (`vertexai.agent_engines` is the
    documented pattern as of Agent Engine's public preview; confirm it still
    applies under the Gemini Enterprise Agent Platform branding).
  - Whether history must be passed as plain dicts (as used here, matching
    assistant.py's existing {"role": ..., "content": ...} shape) or as
    ADK/Vertex `Content`/`Part` objects.
Do not treat the implementation below as verified working code — smoke-test
it against the real deployed agent (agent/tests/test_agent_local.py) before
flipping config.USE_AGENT_ENGINE on for any real traffic.
"""

import time

import config

_engine = None
_engine_init_failed = False


def _get_engine():
    """
    Lazily initializes and caches the Agent Engine client handle. Import is
    deferred so Cloud Run's cold start / requirements.txt don't need the
    Agent Engine SDK unless this path is actually used.
    """
    global _engine, _engine_init_failed

    if _engine is not None:
        return _engine
    if _engine_init_failed:
        raise RuntimeError("Agent Engine client previously failed to initialize.")

    if not config.AGENT_ENGINE_RESOURCE_NAME:
        raise RuntimeError("config.AGENT_ENGINE_RESOURCE_NAME is not set.")
    if not config.GCP_PROJECT:
        raise RuntimeError("config.GCP_PROJECT is not set.")

    try:
        import vertexai
        from vertexai import agent_engines

        vertexai.init(project=config.GCP_PROJECT, location=config.GCP_LOCATION)
        _engine = agent_engines.get(config.AGENT_ENGINE_RESOURCE_NAME)
        return _engine
    except Exception:
        _engine_init_failed = True
        raise


def _history_to_agent_format(pruned_history: list) -> list:
    """
    Translates assistant.py's {"role": "user"|"assistant", "content": str}
    history entries into the shape the deployed agent expects. Kept as a
    pass-through for now since the exact expected shape is unverified
    (see module docstring) — adjust here once confirmed, without touching
    assistant.py's call site.
    """
    return list(pruned_history or [])


def _extract_text(response) -> str:
    """
    Defensively extracts plain text from whatever the Agent Engine query
    call returns, mirroring gpt_test.chat_with_gemini's discipline of
    concatenating all text parts rather than assuming a single string.
    """
    if isinstance(response, str):
        return response

    if isinstance(response, dict):
        # Common shapes seen across ADK/Vertex agent samples: a top-level
        # "output"/"text" string, or an "events"/"content" list with parts.
        if isinstance(response.get("output"), str):
            return response["output"]
        if isinstance(response.get("text"), str):
            return response["text"]
        content = response.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        if parts:
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p)

    # Fall back to string conversion rather than raising, so a shape
    # mismatch degrades to a visibly wrong response instead of a crash --
    # assistant.py's caller-side try/except will still catch outright
    # exceptions and fall back to the direct LLM path.
    return str(response)


def query_agent(caller_input: str, pruned_history: list, phone: str, context: str = "") -> str:
    """
    Sends the current turn to the deployed Agent Engine agent and returns
    its plain-text reply. Raises on any failure so assistant.py's per-turn
    try/except can fall back to the direct gpt_test.chat_with_gpt() path.
    """
    engine = _get_engine()
    agent_history = _history_to_agent_format(pruned_history)

    t_start = time.time()
    # NOTE: `.query(...)` call shape is unverified -- see module docstring.
    # Passing history via a "history" kwarg matches assistant.py's existing
    # sliding-window pattern; confirm the deployed agent's session/query
    # contract actually accepts it this way, or adjust to whatever the
    # confirmed API expects (e.g. a session-based history append instead).
    response = engine.query(
        input=caller_input,
        history=agent_history,
        user_id=phone,
    )
    text = _extract_text(response)
    print(f"[Agent Engine] Phone={phone} latency={int((time.time() - t_start) * 1000)}ms")
    return text
