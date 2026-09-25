"""
Tool(s) exposed to the ADK agent (agent/agent.py). ADK tools are plain
Python functions with type hints and a docstring, which ADK uses to
auto-generate the function-calling schema presented to the model --
confirm this is still the case for the currently-shipping ADK version
(the "Unverified facts" section in the plan flags this as a lower-risk
item since this pattern has been stable across ADK's public samples).
"""

import rag_client


def search_knowledge(query: str) -> str:
    """Looks up Airborne Aviation Academy facts (courses, fees, eligibility,
    schedules, campus location) relevant to the caller's question.

    Args:
        query: A concise description of what the caller is asking about,
            e.g. "CPL ground classes fee" or "cabin crew eligibility age".

    Returns:
        Relevant factual context to answer the caller's question, drawn
        from Airborne Aviation Academy's official course/fee/eligibility
        information.
    """
    return rag_client.query_rag(query)
