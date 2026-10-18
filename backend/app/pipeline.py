import asyncio
import os
import json
import logging
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

# Configuration
MAX_PASSAGES_FOR_LLM = int(os.getenv("MAX_PASSAGES_FOR_LLM", "40"))
JOB_MAX_SECONDS = int(os.getenv("TASK_MAX_SECONDS", "180"))
FETCH_MAX_MB = int(os.getenv("FETCH_MAX_MB", "10"))

# Evidence id pattern used to validate external responses
EVIDENCE_ID_RE = re.compile(r"^evi-[0-9a-f]{12}$")

# Private networks to block for SSRF protections
PRIVATE_NETWORKS = (
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
)

# Lazy imports for external tools/clients
try:
    from .tool_registry import store_document_external, fetch_evidence_external, run_tool
except Exception as e:  # pragma: no cover - defensive
    logger.debug("tool_registry import failed in pipeline: %s", e)
    store_document_external = None  # type: ignore
    fetch_evidence_external = None  # type: ignore
    run_tool = None  # type: ignore

try:
    from .retrieval import validate_url_for_fetch
except Exception:
    # retrieval.validate_url_for_fetch may not be present; we'll provide a local light-weight host check
    validate_url_for_fetch = None  # type: ignore

from .extractors.html_extractor import extract_html_passages
from .extractors.pdf_extractor import extract_pdf_passages
from .report_schema import validate_report


# Utility helpers
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


# Minimal synchronous fetch with redirect validation and SSRF protections.
# This is intentionally conservative for the pipeline. For production use, reuse the dedicated retrieval module.
def fetch_url_sync(url: str) -> Dict[str, Any]:
    import httpx
    import socket
    import ipaddress
    from urllib.parse import urlparse, urljoin

    def _is_private_ip(ip_str: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip_str)
        except Exception:
            return True
        for net in PRIVATE_NETWORKS:
            if addr in ipaddress.ip_network(net):
                return True
        return False

    def _resolve(hostname: str):
        try:
            infos = socket.getaddrinfo(hostname, None)
            return {info[4][0] for info in infos}
        except Exception:
            return set()

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise RuntimeError("unsupported or invalid URL scheme/hostname")

    # Pre-resolve and block private IPs
    ips = _resolve(parsed.hostname)
    if not ips:
        raise RuntimeError("dns resolution failed for host")
    for ip in ips:
        if _is_private_ip(ip):
            raise RuntimeError("destination resolves to private IP")

    TIMEOUT = httpx.Timeout(10.0, read=30.0)
    MAX_REDIRECTS = 5
    current = url
    redirects = 0

    while True:
        with httpx.Client(follow_redirects=False, timeout=TIMEOUT) as client:
            r = client.get(current, headers={"User-Agent": "fineprint-sherpa/0.1 (+https://github.com)"})
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("location")
            if not loc:
                raise RuntimeError("redirect with no Location header")
            next_url = urljoin(current, loc)
            redirects += 1
            if redirects > MAX_REDIRECTS:
                raise RuntimeError("too many redirects")
            # validate next host
            nparsed = urlparse(next_url)
            nips = _resolve(nparsed.hostname) if nparsed.hostname else set()
            if not nips:
                raise RuntimeError("dns resolution failed on redirect")
            for ip in nips:
                if _is_private_ip(ip):
                    raise RuntimeError("redirect resolves to private IP")
            current = next_url
            continue
        break

    content_type = r.headers.get("content-type", "")
    content_length = int(r.headers.get("content-length") or len(r.content))
    if content_length > FETCH_MAX_MB * 1024 * 1024:
        raise RuntimeError("content too large")

    return {
        "status_code": r.status_code,
        "final_url": str(r.url),
        "content_type": content_type,
        "content": r.content,
        "headers": dict(r.headers),
    }


# Main orchestrator
def run_analysis_job(job_id: str, url: str, objective: str | None):
    """Main orchestrator for a single analysis job.
    Enforces execution-time validation of tool inputs/outputs and uses an external-only
    terms adapter for persistence. Fails closed on missing external service unless
    explicit test/mock opt-in is configured.
    """
    start_time = time.monotonic()
    with JOB_LOCK:
        JOB_CANCEL[job_id] = False
        JOB_STATUS[job_id] = {"status": "queued"}

    try:
        _set_job_status(job_id, {"status": "running", "phase": "fetching"})
        # Use synchronous safe fetch
        fetched = fetch_url_sync(url)
        content_type = (fetched.get("content_type") or "")
        final_url = fetched["final_url"]
        if _is_cancelled(job_id):
            raise RuntimeError("cancelled during fetch")

        _set_job_status(job_id, {"status": "running", "phase": "extracting", "final_url": final_url})
        if "pdf" in content_type.lower() or final_url.lower().endswith('.pdf'):
            extracted = extract_pdf_passages(fetched["content"], final_url)
        else:
            extracted = extract_html_passages(fetched["content"], final_url)

        if not extracted or "passages" not in extracted or len(extracted["passages"]) == 0:
            raise RuntimeError("extraction failed or returned no passages")

        if _is_cancelled(job_id):
            raise RuntimeError("cancelled during extraction")

        # Persist extracted passages to external terms service (fail-closed)
        _set_job_status(job_id, {"status": "running", "phase": "storing_evidence", "count": len(extracted["passages"])})
        store_payload = {"final_url": final_url, "passages": extracted["passages"]}

        if run_tool is None or store_document_external is None:
            raise RuntimeError("tool registry or external storage not configured")

        try:
            evidences = run_tool("extract_document", lambda final_url, passages: store_document_external(final_url, passages), store_payload)
        except Exception as e:
            raise RuntimeError(f"external_store_error: {e}")

        if not isinstance(evidences, (list, tuple)) or len(evidences) == 0:
            raise RuntimeError("external terms service returned no evidence ids or invalid shape")

        # Validate evidence id shapes
        bad_ids = [e for e in evidences if not isinstance(e, str) or not EVIDENCE_ID_RE.match(e)]
        if bad_ids:
            raise RuntimeError(f"external returned evidence ids with invalid shape: {bad_ids}")

        if _is_cancelled(job_id):
            raise RuntimeError("cancelled during storing evidence")

        # Deterministic extraction of candidate findings
        findings: List[Dict[str, Any]] = []
        evidence_set = set(evidences)
        for p in extracted["passages"]:
            txt = p.get("text", "").lower()
            eid = p.get("evidence_id")
            # Only consider findings if the passage has a valid evidence id returned by the external store
            if eid and eid in evidence_set and any(k in txt for k in ("cancel", "termination", "renew")):
                findings.append({"text": p.get("text", "")[:400], "evidence": [eid]})

        _set_job_status(job_id, {"status": "running", "phase": "analysis", "evidence_count": len(evidences)})

        # Fetch evidence content from external store and validate provenance
        try:
            evidence_map = fetch_evidence_external(evidences, final_url)
        except Exception as e:
            raise RuntimeError(f"external_fetch_error: {e}")

        if not isinstance(evidence_map, dict):
            raise RuntimeError("external fetch returned unexpected shape")

        validated_findings: List[Dict[str, Any]] = []
        unsupported: List[str] = []

        for f in findings:
            evs = f.get("evidence", [])
            valid = True
            provenance: Dict[str, str] = {}
            for ev in evs:
                if ev not in evidence_map:
                    valid = False
                    unsupported.append(ev)
                else:
                    provenance[ev] = evidence_map[ev]
            if valid:
                # Heuristic provenance match: ensure the finding text is present in one of the passages
                supported = False
                for ev, passage_text in provenance.items():
                    if f["text"][:80].strip().lower() in passage_text.strip().lower() or passage_text.strip().lower() in f["text"].strip().lower():
                        supported = True
                        break
                if not supported:
                    raise RuntimeError("provenance check failed: finding text does not match cited passage")
                f["provenance"] = provenance
                validated_findings.append(f)

        # If any finding lacked verifiable evidence, we reject the report (fail-closed)
        if unsupported:
            raise RuntimeError(f"Unsupported evidence IDs referenced in findings: {unsupported}")

        report: Dict[str, Any] = {
            "job_id": job_id,
            "source": {"original_url": url, "final_url": final_url},
            "evidence_count": len(evidences),
            "findings": validated_findings,
            "executive_summary": {"summary": "Deterministic summary: findings enumerated with provenance", "citations": list(evidence_map.keys())},
            "evidence_index": evidence_map,
            "_trace": {"started_at": start_time, "duration_seconds": time.monotonic() - start_time},
        }

        # Validate report schema before accepting it
        validate_report(report)

        # Store report in memory only (application-level job store). Persistent storage of documents is external-only.
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
