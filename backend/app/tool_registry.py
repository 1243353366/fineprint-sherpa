import logging
from .tool_schema_loader import validate_input, validate_output
from .external_terms import get_terms_client

logger = logging.getLogger(__name__)
TERMS = None
try:
    TERMS = get_terms_client()
except Exception as e:
    # Do not raise here — caller must handle. But log the issue.
    logger.warning("External terms client not available: %s", e)


def run_tool(tool_name: str, func, payload: dict):
    """Validate inputs, execute tool function, validate outputs."""
    validate_input(tool_name, payload)
    result = func(**payload)
    # If result is not a dict, wrap it
    if result is None:
        result = {}
    if not isinstance(result, dict):
        # allow certain tools to return list or primitive — caller's responsibility
        return result
    validate_output(tool_name, result)
    return result

def store_document_external(final_url: str, passages: list):
    if TERMS is None:
        raise RuntimeError("External terms client not configured — cannot store document")
    # tool-level payload validation
    payload = {"final_url": final_url, "passages": passages}
    # No specific tool schema here; just call the client
    return TERMS.store_document(final_url, passages)

def fetch_evidence_external(evidence_ids: list, final_url: str):
    if TERMS is None:
        raise RuntimeError("External terms client not configured — cannot fetch evidence")
    return TERMS.get_evidence(evidence_ids, final_url)
