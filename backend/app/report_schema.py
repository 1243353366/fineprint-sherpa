from jsonschema import validate, ValidationError

REPORT_SCHEMA = {
    "type": "object",
    "required": ["job_id", "source", "evidence_count", "executive_summary", "evidence_index"],
    "properties": {
        "job_id": {"type": "string"},
        "source": {
            "type": "object",
            "required": ["original_url", "final_url"],
            "properties": {
                "original_url": {"type": "string"},
                "final_url": {"type": "string"}
            }
        },
        "evidence_count": {"type": "integer"},
        "findings": {"type": "array"},
        "executive_summary": {"type": "object"},
        "evidence_index": {"type": "object"}
    }
}


def validate_report(report: dict):
    try:
        validate(instance=report, schema=REPORT_SCHEMA)
    except ValidationError as e:
        raise ValueError(f"Report schema validation error: {e.message}")
    return True
