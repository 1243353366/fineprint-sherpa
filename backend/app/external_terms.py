import os
import requests
import logging
from typing import List, Dict, Any

TERMS_API_BASE = os.getenv("TERMS_API_BASE")
TERMS_API_KEY = os.getenv("TERMS_API_KEY")
EXTERNAL_TERMS_ALLOW_MOCK = os.getenv("EXTERNAL_TERMS_ALLOW_MOCK", "false").lower() in ("1", "true", "yes")

logger = logging.getLogger(__name__)


class ExternalTermsError(Exception):
    pass


class ExternalTermsClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url or os.getenv("TERMS_API_BASE")
        self.api_key = api_key or os.getenv("TERMS_API_KEY")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def _require_remote(self):
        if not self.base_url:
            raise ExternalTermsError("TERMS_API_BASE not configured; external persistence is required")

    def store_document(self, final_url: str, passages: List[Dict[str, Any]]) -> Dict[str, Any]:
        self._require_remote()
        endpoint = f"{self.base_url.rstrip('/')}/documents"
        payload = {"final_url": final_url, "passages": passages}
        r = self.session.post(endpoint, json=payload, timeout=30)
        if r.status_code >= 300:
            logger.error("Failed to store document on external terms API: %s %s", r.status_code, r.text)
            raise ExternalTermsError(f"external store failed: {r.status_code}")
        data = r.json()
        # External contract: return evidence_map keyed by passage index or stable local id.
        evidence_map = data.get("evidence_map") or {}
        if not isinstance(evidence_map, dict):
            evidence_ids = data.get("evidence_ids") or []
            evidence_map = {str(i): eid for i, eid in enumerate(evidence_ids)}
        return {"document_id": data.get("document_id", final_url), "evidence_map": evidence_map}

    def get_evidence(self, evidence_ids: List[str], final_url: str) -> Dict[str, str]:
        self._require_remote()
        ids_param = ",".join(evidence_ids)
        endpoint = f"{self.base_url.rstrip('/')}/documents/evidence"
        params = {"final_url": final_url, "ids": ids_param}
        r = self.session.get(endpoint, params=params, timeout=30)
        if r.status_code >= 300:
            logger.error("Failed to fetch evidence from external terms API: %s %s", r.status_code, r.text)
            raise ExternalTermsError(f"external fetch failed: {r.status_code}")
        data = r.json()
        return data.get("evidence", {})


class MockExternalTermsClient(ExternalTermsClient):
    def __init__(self):
        self.docs: Dict[str, Dict[str, str]] = {}

    def store_document(self, final_url: str, passages: List[Dict[str, Any]]) -> Dict[str, Any]:
        existing = self.docs.get(final_url, {})
        evidence_map: Dict[str, str] = {}
        for idx, passage in enumerate(passages):
            text = passage.get("text") or ""
            evidence_id = passage.get("evidence_id") or f"evi-{idx:012x}"
            evidence_map[str(idx)] = evidence_id
            existing[evidence_id] = text
        self.docs[final_url] = existing
        return {"document_id": final_url, "evidence_map": evidence_map}

    def get_evidence(self, evidence_ids: List[str], final_url: str) -> Dict[str, str]:
        evidence_map = self.docs.get(final_url, {})
        return {eid: evidence_map[eid] for eid in evidence_ids if eid in evidence_map}


def get_terms_client():
    if TERMS_API_BASE:
        return ExternalTermsClient(TERMS_API_BASE, TERMS_API_KEY)
    if EXTERNAL_TERMS_ALLOW_MOCK:
        logger.warning("TERMS_API_BASE not set, but EXTERNAL_TERMS_ALLOW_MOCK=true — using non-persistent in-memory mock (TEST MODE)")
        return MockExternalTermsClient()
    raise ExternalTermsError("TERMS_API_BASE is not configured and mock usage is not allowed in this environment")
