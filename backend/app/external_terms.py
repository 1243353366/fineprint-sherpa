# External terms API adapter for FinePrint Sherpa
# This module sends extracted passages to an external terms-and-conditions service
# and retrieves evidence passages by ID. The adapter is pluggable via TERMS_API_BASE.

import os
import requests
import logging
from typing import List, Dict

TERMS_API_BASE = os.getenv("TERMS_API_BASE")  # e.g. https://terms.example.com/api
TERMS_API_KEY = os.getenv("TERMS_API_KEY")

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
            raise ExternalTermsError("TERMS_API_BASE not configured; external persistence is required for production")

    def store_document(self, final_url: str, passages: List[Dict]) -> List[str]:
        """
        POST /documents
        Body: { final_url, passages: [{ evidence_id, text, page_number, heading, tag }] }
        Response: { document_id, evidence_ids: [...] }
        """
        self._require_remote()
        endpoint = f"{self.base_url.rstrip('/')}/documents"
        payload = {"final_url": final_url, "passages": passages}
        r = self.session.post(endpoint, json=payload, timeout=30)
        if r.status_code >= 300:
            logger.error("Failed to store document on external terms API: %s %s", r.status_code, r.text)
            raise ExternalTermsError(f"external store failed: {r.status_code}")
        data = r.json()
        return data.get("evidence_ids", [])

    def get_evidence(self, evidence_ids: List[str], final_url: str) -> Dict[str, str]:
        """
        GET /documents/evidence?final_url=...&ids=id1,id2
        Response: { evidence: { evidence_id: text, ... } }
        """
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

# Mock client (in-memory) for local testing ONLY. It does not persist across restarts.
class MockExternalTermsClient(ExternalTermsClient):
    def __init__(self):
        super().__init__(base_url=None, api_key=None)
        self.docs = {}

    def store_document(self, final_url: str, passages: List[Dict]) -> List[str]:
        # store in-memory keyed by final_url
        existing = self.docs.get(final_url, {})
        evidence_map = existing.copy()
        for p in passages:
            evidence_map[p["evidence_id"]] = p["text"]
        self.docs[final_url] = evidence_map
        return list(evidence_map.keys())

    def get_evidence(self, evidence_ids: List[str], final_url: str) -> Dict[str, str]:
        evidence_map = self.docs.get(final_url, {})
        out = {eid: evidence_map[eid] for eid in evidence_ids if eid in evidence_map}
        return out

# Factory
def get_terms_client():
    if TERMS_API_BASE:
        return ExternalTermsClient(TERMS_API_BASE, TERMS_API_KEY)
    logger.warning("TERMS_API_BASE not set, using in-memory mock external client (non-persistent)")
    return MockExternalTermsClient()
