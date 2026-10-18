from .external_terms import get_terms_client
from .tool_schema_loader import load_all_schemas, get_tool_schema

SCHEMAS = load_all_schemas()
TERMS = get_terms_client()

def validate_tool_call(tool_name: str, payload: dict) -> bool:
    schema = get_tool_schema(tool_name)
    if not schema:
        return True
    # minimal validation: required fields
    required = schema.get("input", {}).get("required", [])
    for r in required:
        if r not in payload:
            raise ValueError(f"Missing required field for {tool_name}: {r}")
    return True

def store_document_external(final_url: str, passages: list):
    # Delegates to external terms storage
    return TERMS.store_document(final_url, passages)

def fetch_evidence_external(evidence_ids: list, final_url: str):
    return TERMS.get_evidence(evidence_ids, final_url)
