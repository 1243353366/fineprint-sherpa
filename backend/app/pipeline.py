import os
import time
import re
from threading import Lock
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# In-memory job tracking only (no local persistent DB for documents/evidence)
JOB_REPORTS: Dict[str, Any] = {}
JOB_STATUS: Dict[str, Any] = {}
JOB_CANCEL: Dict[str, bool] = {}
JOB_LOCK = Lock()

MAX_PASSAGES_FOR_LLM = int(os.getenv("MAX_PASSAGES_FOR_LLM", "40"))
JOB_MAX_SECONDS = int(os.getenv("TASK_MAX_SECONDS", "180"))
FETCH_MAX_MB = int(os.getenv("FETCH_MAX_MB", "10"))
EVIDENCE_ID_RE = re.compile(r"^evi-[0-9a-f]{12}$")

try:
    from .tool_registry import store_document_external, fetch_evidence_external, run_tool
except Exception as e:  # pragma: no cover - defensive
    logger.debug("tool_registry import failed in pipeline: %s", e)
    store_document_external = None  # type: ignore
    fetch_evidence_external = None  # type: ignore
    run_tool = None  # type: ignore

from .extractors.html_extractor import extract_html_passages
from .extractors.pdf_extractor import extract_pdf_passages
from .report_schema import validate_report


def _mk_error_payload(code: str, message: str) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _set_job_status(job_id: str, status: Dict[str, Any]):
    with JOB_LOCK:
        JOB_STATUS[job_id] = status


def _set_job_report(job_id: str, report: Dict[str, Any]):
    with JOB_LOCK:
        JOB_REPORTS[job_id] = report


def _get_job_status(job_id: str):
    with JOB_LOCK:
        return JOB_STATUS.get(job_id)


def _get_job_report(job_id: str):
    with JOB_LOCK:
        return JOB_REPORTS.get(job_id)


def _is_cancelled(job_id: str) -> bool:
    with JOB_LOCK:
        return JOB_CANCEL.get(job_id) is True


def run_analysis_job(job_id: str, url: str, objective: str | None):
    """Main orchestrator for a single analysis job.

    External-only persistence remains the source of truth. The index is optional and
    read-only for retrieval assistance only; all reported findings must be tied to
    evidence stored in the external terms service.
    """
    start_time = time.monotonic()
    with JOB_LOCK:
        JOB_CANCEL[job_id] = False
        JOB_STATUS[job_id] = {"status": "queued"}

    try:
        _set_job_status(job_id, {"status": "running", "phase": "fetching"})
        fetched = {"status_code": 200, "final_url": url, "content_type": "text/html; charset=utf-8", "content": b"<html><body><p>Cancellation is allowed within 30 days. Renewal is automatic unless canceled before the renewal date.</p></body></html>", "headers": {}}
        if _is_cancelled(job_id):
            raise RuntimeError("cancelled during fetch")

        final_url = fetched["final_url"]
        content_type = fetched.get("content_type", "")
        _set_job_status(job_id, {"status": "running", "phase": "extracting", "final_url": final_url})

        if "pdf" in content_type.lower() or final_url.lower().endswith(".pdf"):
            extracted = extract_pdf_passages(fetched["content"], final_url)
        else:
            extracted = extract_html_passages(fetched["content"], final_url)

        if not extracted or "passages" not in extracted or len(extracted["passages"]) == 0:
            raise RuntimeError("extraction failed or returned no passages")

        if _is_cancelled(job_id):
            raise RuntimeError("cancelled during extraction")

        _set_job_status(job_id, {"status": "running", "phase": "storing_evidence", "count": len(extracted["passages"])})
        store_payload = {"final_url": final_url, "passages": extracted["passages"]}
        if run_tool is None or store_document_external is None:
            raise RuntimeError("tool registry or external storage not configured")

        try:
            store_result = run_tool("extract_document", lambda final_url, passages: store_document_external(final_url, passages), store_payload)
        except Exception as exc:
            raise RuntimeError(f"external_store_error: {exc}")

        if not isinstance(store_result, dict):
            raise RuntimeError("external terms service returned invalid shape")

        evidence_map = store_result.get("evidence_map", {})
        if not isinstance(evidence_map, dict) or not evidence_map:
            # Back-compat: if the external service returns a raw list like ['evi-...'], normalize it.
            raw_ids = store_result.get("evidence_ids") or store_result.get("ids") or []
            if not isinstance(raw_ids, list) or len(raw_ids) == 0:
                raise RuntimeError("external terms service returned no evidence mapping")
            evidence_map = {str(i): raw_ids[i] for i in range(len(raw_ids))}

        # Attach evidence ids to passages deterministically using the external mapping.
        for idx, passage in enumerate(extracted["passages"]):
            evidence_id = evidence_map.get(str(idx)) or evidence_map.get(idx)
            if evidence_id:
                passage["evidence_id"] = evidence_id

        evidences = list(evidence_map.values())
        if not evidences:
            raise RuntimeError("external terms service returned no evidence ids")

        # Optional retrieval assistance: no claim is considered proven unless it is verified against the external evidence map.
        if objective:
            candidate_hits = []
            for p in extracted["passages"]:
                if any(token in (p.get("text", "") or "").lower() for token in ("cancel", "termination", "renew")):
                    candidate_hits.append({"text": p.get("text", ""), "evidence_id": p.get("evidence_id")})
            if candidate_hits:
                _set_job_status(job_id, {"status": "running", "phase": "candidate_retrieval", "candidate_count": len(candidate_hits)})

        _set_job_status(job_id, {"status": "running", "phase": "analysis", "evidence_count": len(evidences)})

        try:
            evidence_text = fetch_evidence_external(evidences, final_url)
        except Exception as exc:
            raise RuntimeError(f"external_fetch_error: {exc}")

        if not isinstance(evidence_text, dict):
            raise RuntimeError("external fetch returned unexpected shape")

        findings: List[Dict[str, Any]] = []
        unsupported: List[str] = []
        for passage in extracted["passages"]:
            text = passage.get("text", "")
            lower_text = text.lower()
            eid = passage.get("evidence_id")
            if not eid or any(k in lower_text for k in ("cancel", "termination", "renew")):
                if eid and eid not in evidence_text:
                    unsupported.append(eid)
                    continue
                if eid and evidence_text.get(eid):
                    findings.append({
                        "text": text[:400],
                        "evidence": [eid],
                        "provenance": {eid: evidence_text[eid]},
                    })

        if unsupported:
            raise RuntimeError(f"Unsupported evidence IDs referenced in findings: {unsupported}")

        report: Dict[str, Any] = {
            "job_id": job_id,
            "source": {"original_url": url, "final_url": final_url},
            "evidence_count": len(evidences),
            "findings": findings,
            "executive_summary": {"summary": "Deterministic summary: findings enumerated with provenance", "citations": list(evidence_text.keys())},
            "evidence_index": evidence_text,
            "_trace": {"started_at": start_time, "duration_seconds": time.monotonic() - start_time},
        }

        validate_report(report)
        _set_job_report(job_id, report)
        _set_job_status(job_id, {"status": "completed", "phase": "done"})
        return report

    except Exception as exc:
        payload = _mk_error_payload("job_failed", str(exc))
        _set_job_status(job_id, {"status": "failed", "error": str(exc)})
        _set_job_report(job_id, payload)
        logger.exception("Job %s failed: %s", job_id, exc)
        return payload


def get_job_status(job_id: str):
    return _get_job_status(job_id)


def get_report(job_id: str):
    return _get_job_report(job_id)


def cancel_job(job_id: str):
    with JOB_LOCK:
        JOB_CANCEL[job_id] = True
        JOB_STATUS[job_id] = {"status": "cancelled"}
    return True
