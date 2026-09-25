"""
RAG lookup used by the agent's search_knowledge tool (agent/tools.py).

Design decision (see plan): RAG stays canonical in Cloud Run (rag.py +
Postgres/pgvector), reached over HTTP via the new /internal/rag/query
endpoint on the existing Cloud Run service, rather than giving this
Agent Engine deployment its own direct Cloud SQL connection. Rationale:
Cloud Run already has a proven Cloud SQL Auth Proxy connection; Agent
Engine's VPC/Cloud SQL connectivity is unverified and duplicating DB
credentials/connection logic into a second deployable is unnecessary risk.
Revisit if Agent Engine's direct DB connectivity is confirmed to work
cleanly later.

Falls back to the local static knowledge_base.search_local_knowledge() if
the HTTP call fails for any reason (mirrors rag.py's own
pgvector -> local-KB fallback chain, with this as an outer HTTP-failure
layer on top).
"""

import os

import requests

import knowledge_base

RAG_ENDPOINT_URL = os.environ.get("RAG_ENDPOINT_URL", "")
INTERNAL_RAG_SHARED_SECRET = os.environ.get("INTERNAL_RAG_SHARED_SECRET", "")

_TIMEOUT_SECONDS = 5


def query_rag(query: str, limit: int = 3) -> str:
    if RAG_ENDPOINT_URL and INTERNAL_RAG_SHARED_SECRET:
        try:
            response = requests.post(
                RAG_ENDPOINT_URL,
                json={"query": query, "limit": limit},
                headers={"X-Internal-Secret": INTERNAL_RAG_SHARED_SECRET},
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            context = data.get("context")
            if context:
                return context
        except Exception as e:
            print(f"[agent/rag_client] RAG endpoint call failed ({e}). Falling back to local knowledge base.")
    else:
        print("[agent/rag_client] RAG_ENDPOINT_URL/INTERNAL_RAG_SHARED_SECRET not set. Using local knowledge base.")

    return knowledge_base.search_local_knowledge(query, top_k=limit)
