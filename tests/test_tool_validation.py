import os
import pytest
from backend.app.tool_schema_loader import validate_input, validate_output


def test_tool_input_validation_missing_required():
    # fetch_url requires 'url' in input
    with pytest.raises(ValueError):
        validate_input("fetch_url", {})


def test_tool_output_validation_wrong_shape():
    # simulate output missing required key
    bad_output = {"final_url": "https://example.com"}
    with pytest.raises(ValueError):
        validate_output("fetch_url", bad_output)
