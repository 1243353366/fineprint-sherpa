# Integration test that runs only when RUN_INTEGRATION_TESTS=1 is set in the environment.

import os
import pytest
from backend.app.pipeline import run_analysis_job, get_report

RUN_INTEGRATION = os.getenv("RUN_INTEGRATION_TESTS", "0") == "1"

@pytest.mark.skipif(not RUN_INTEGRATION, reason="Integration tests require network and are skipped by default")
def test_public_url_integration():
    job_id = "integration-example-com"
    url = "https://example.com"
    run_analysis_job(job_id, url, "Integration test: summarize")
    report = get_report(job_id)
    assert report is not None
    assert report.get("source", {}).get("final_url") is not None
    assert report.get("evidence_count", 0) >= 1
    evidence_index = report.get("evidence_index") or {}
    assert isinstance(evidence_index, dict)
    assert len(evidence_index) >= 1
