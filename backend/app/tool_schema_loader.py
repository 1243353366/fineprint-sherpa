import json
from pathlib import Path
import yaml
from jsonschema import validate, ValidationError

SCHEMA_PATH = Path(__file__).parent / "tool_schemas.yaml"

def load_all_schemas():
    if not SCHEMA_PATH.exists():
        return {}
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_tool_schema(name: str):
    all_s = load_all_schemas()
    return all_s.get(name)

def validate_input(tool_name: str, payload: dict):
    schema = get_tool_schema(tool_name)
    if not schema:
        return True
    input_schema = schema.get("input")
    if not input_schema:
        return True
    try:
        validate(instance=payload, schema=input_schema)
    except ValidationError as e:
        raise ValueError(f"Tool {tool_name} input validation error: {e.message}")
    return True

def validate_output(tool_name: str, output: dict):
    schema = get_tool_schema(tool_name)
    if not schema:
        return True
    out_schema = schema.get("output")
    if not out_schema:
        return True
    try:
        validate(instance=output, schema=out_schema)
    except ValidationError as e:
        raise ValueError(f"Tool {tool_name} output validation error: {e.message}")
    return True
