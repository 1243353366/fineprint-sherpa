import os
import logging
from typing import Any, Dict, List

from .external_terms import get_terms_client
from .rag_adapter import index_passages, llm_assisted_candidates

logger = logging.getLogger(__name__)

TERMS = None
try:
    TERMS = get_terms_client()
except Exception as e:
    logger.warning("External terms client not available: %s", e)


def run_tool(tool_name: str, func, payload: dict):
    """Validate inputs, execute tool function, validate outputs."""
    from .tool_schema_loader import validate_input, validate_output
    validate_input(tool_name, payload)
    result = func(**payload)
    if result is None:
        result = {}
    if not isinstance(result, dict):
        return result
    validate_output(tool_name, result)
    return result


def store_document_external(final_url: str, passages: list):
    if TERMS is None:
        raise RuntimeError("External terms client not configured — cannot store document")
    result = TERMS.store_document(final_url, passages)
    # Preserve the authoritative external mapping and also index it for retrieval assistance.
    evidence_map = result.get("evidence_map", {}) if isinstance(result, dict) else {}
    if evidence_map:
        index_passages(final_url, passages, evidence_map)
    return result


def fetch_evidence_external(evidence_ids: list, final_url: str):
    if TERMS is None:
        raise RuntimeError("External terms client not configured — cannot fetch evidence")
    return TERMS.get_evidence(evidence_ids, final_url)


def suggest_candidates(query: str, k: int = 8, objective: str | None = None):
    return llm_assisted_candidates(query, k=k, objective=objective)
