import os
import pytest
from backend.app.external_terms import MockExternalTermsClient
from backend.app.pipeline import run_analysis_job


def test_unknown_evidence_rejected(monkeypatch):
    # Setup mock external client and ensure pipeline uses it
    monkeypatch.setenv("EXTERNAL_TERMS_ALLOW_MOCK", "true")
    from backend.app.tool_registry import TERMS
    # Force a mock client
    from backend.app.external_terms import MockExternalTermsClient
    monkeypatch.setenv("TERMS_API_BASE", "")
    client = MockExternalTermsClient()
    # Empty storage to simulate missing evidence
    client.docs = {}
    # Monkeypatch tool_registry.TERMS to our client
    import importlib
    tr = importlib.import_module("backend.app.tool_registry")
    tr.TERMS = client

    # Run pipeline with a small synthetic HTML that will produce a finding referencing an evidence id
    job_id = "test-unknown-ev"
    url = "https://example.com/test-unknown"

    # Monkeypatch fetch_url to return controlled HTML
    from backend.app.retrieval import fetch_url as real_fetch
    def fake_fetch(u):
        return {"status_code": 200, "final_url": url, "content_type": "text/html", "content": b"<html><body><p>Cancel within 30 days</p></body></html>", "headers": {}}
    monkeypatch.setattr("backend.app.pipeline.fetch_url", lambda u: fake_fetch(u))

    result = run_analysis_job(job_id, url, "Summarize")
    assert isinstance(result, dict)
    assert "error" in result
    assert "Unsupported evidence IDs" in result["error"]
