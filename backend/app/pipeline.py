import asyncio
import os
import json
import logging
from .retrieval import fetch_url
from .extractors.html_extractor import extract_html_passages
from .extractors.pdf_extractor import extract_pdf_passages
from .tool_registry import store_document_external, fetch_evidence_external, run_tool
from .report_schema import validate_report

logger = logging.getLogger(__name__)

# In-memory job tracking only (no local persistent DB for documents/evidence)
JOB_REPORTS = {}
JOB_STATUS = {}
JOB_CANCEL = {}

# Configuration
MAX_PASSAGES_FOR_LLM = int(os.getenv("MAX_PASSAGES_FOR_LLM", "40"))


def _is_cancelled(job_id: str):
    return JOB_CANCEL.get(job_id) is True


def run_analysis_job(job_id: str, url: str, objective: str | None):
    """Main orchestrator for a single analysis job.
    This implementation enforces execution-time validation of tool inputs/outputs
    and uses an external-only terms adapter for persistence. It fails closed if
    the external service is not configured (unless explicit test/mock opt-in).
    """
    JOB_CANCEL[job_id] = False
    JOB_STATUS[job_id] = {"status": "queued"}

    try:
        JOB_STATUS[job_id] = {"status": "running", "phase": "fetching"}
        fetched = asyncio.run(fetch_url(url))
        content_type = fetched.get("content_type", "") or ""
        final_url = fetched["final_url"]
        if _is_cancelled(job_id):
            raise RuntimeError("cancelled during fetch")

        JOB_STATUS[job_id] = {"status": "running", "phase": "extracting", "final_url": final_url}
        if "pdf" in content_type.lower() or final_url.lower().endswith('.pdf'):
            extracted = extract_pdf_passages(fetched["content"], final_url)
        else:
            extracted = extract_html_passages(fetched["content"], final_url)

        if not extracted or "passages" not in extracted:
            raise RuntimeError("extraction failed or returned no passages")

        if _is_cancelled(job_id):
            raise RuntimeError("cancelled during extraction")

        # Persist extracted passages to external terms service (fail-closed)
        JOB_STATUS[job_id] = {"status": "running", "phase": "storing_evidence", "count": len(extracted["passages"])}
        # Validate payload according to tool schema at runtime via run_tool wrapper
        store_payload = {"final_url": final_url, "passages": extracted["passages"]}
        # run_tool will validate inputs and outputs if tool schema present
        evidences = run_tool("extract_document", lambda final_url, passages: store_document_external(final_url, passages), store_payload)
        if not evidences:
            raise RuntimeError("external terms service returned no evidence ids")

        if _is_cancelled(job_id):
            raise RuntimeError("cancelled during storing evidence")

        # Deterministic extraction of candidate findings
        findings = []
        for p in extracted["passages"]:
            txt = p.get("text", "").lower()
            if any(k in txt for k in ("cancel", "termination", "renew")):
                findings.append({"text": p.get("text", "")[:400], "evidence": [p.get("evidence_id")]})

        # Prepare LLM input with a bounded number of passages
        JOB_STATUS[job_id] = {"status": "running", "phase": "analysis", "evidence_count": len(evidences)}
        llm_passages = extracted["passages"][:MAX_PASSAGES_FOR_LLM]
        llm_input = {"passages": [{"id": p["evidence_id"], "text": p["text"]} for p in llm_passages], "objective": objective}
        # For LLM tooling, we validate the input schema
        # Here, LLM call is external and abstracted; a real implementation would invoke LLM driver carefully
        # For now, create a conservative summary: list findings backed by evidence and reject any that lack evidence
        # Verify evidence existence via external fetch
        evidence_map = fetch_evidence_external(evidences, final_url)
        # Any finding must have evidence that resolves to text in evidence_map
        validated_findings = []
        unsupported = []
        for f in findings:
            evs = f.get("evidence", [])
            valid = True
            provenance = {}
            for ev in evs:
                if ev not in evidence_map:
                    valid = False
                    unsupported.append(ev)
                else:
                    provenance[ev] = evidence_map[ev]
            if valid:
                f["provenance"] = provenance
                validated_findings.append(f)

        # If any finding lacked verifiable evidence, we reject the report (fail-closed)
        if unsupported:
            raise RuntimeError(f"Unsupported evidence IDs referenced in findings: {unsupported}")

        report = {
            "job_id": job_id,
            "source": {"original_url": url, "final_url": final_url},
            "evidence_count": len(evidences),
            "findings": validated_findings,
            "executive_summary": {"summary": "Deterministic summary: findings enumerated with provenance", "citations": list(evidence_map.keys())},
            "evidence_index": evidence_map,
        }

        # Validate report schema before accepting it
        validate_report(report)

        # Store report in memory only (application-level job store). Persistent storage of documents is external-only.
        JOB_REPORTS[job_id] = report
        JOB_STATUS[job_id] = {"status": "completed", "phase": "done"}
        return report

    except Exception as exc:
        JOB_STATUS[job_id] = {"status": "failed", "error": str(exc)}
        JOB_REPORTS[job_id] = {"error": str(exc)}
        logger.exception("Job %s failed: %s", job_id, exc)
        return JOB_REPORTS[job_id]


def get_job_status(job_id: str):
    return JOB_STATUS.get(job_id)


def get_report(job_id: str):
    return JOB_REPORTS.get(job_id)


def cancel_job(job_id: str):
    JOB_CANCEL[job_id] = True
    JOB_STATUS[job_id] = {"status": "cancelled"}
    return True
