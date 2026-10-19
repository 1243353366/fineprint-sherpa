from __future__ import annotations

import math
from typing import Dict, Iterable, List, Tuple


class InMemoryVectorIndex:
    """Minimal vector-like index used for candidate retrieval only.

    This is not authoritative evidence storage. Every result must be verified
    against the external terms store before it can be used in a report.
    """

    def __init__(self):
        self._entries: List[Dict[str, object]] = []

    def clear(self):
        self._entries.clear()

    def upsert(self, final_url: str, passages: Iterable[Dict[str, object]], evidence_map: Dict[str, str]) -> None:
        for idx, passage in enumerate(passages):
            text = str(passage.get("text", "")).strip()
            if not text:
                continue
            key = str(idx)
            evidence_id = evidence_map.get(key) or evidence_map.get(idx)
            if not evidence_id:
                continue
            self._entries.append(
                {
                    "final_url": final_url,
                    "evidence_id": evidence_id,
                    "text": text,
                    "metadata": {"passage_index": idx},
                }
            )

    def search(self, query: str, k: int = 8) -> List[Dict[str, object]]:
        if not query:
            return []

        q_tokens = [t.lower() for t in query.split() if t]
        if not q_tokens:
            return []

        scored: List[Tuple[float, Dict[str, object]]] = []
        for entry in self._entries:
            text = str(entry["text"]).lower()
            score = 0.0
            for token in q_tokens:
                if token in text:
                    score += 1.0
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for _, entry in scored[:k]:
            results.append({
                "evidence_id": entry["evidence_id"],
                "text": entry["text"],
                "score": entry.get("score", 0.0),
                "metadata": entry.get("metadata", {}),
            })
        return results


_INDEX = InMemoryVectorIndex()


def index_passages(final_url: str, passages: List[Dict[str, object]], evidence_map: Dict[str, str]) -> None:
    """Index passages for candidate retrieval.

    Important: the vector store is not authoritative. Any claim derived here must be
    verified against the external terms service before it can be reported.
    """
    _INDEX.upsert(final_url, passages, evidence_map)


def clear_index() -> None:
    _INDEX.clear()


def retrieve_candidates(query: str, k: int = 8) -> List[Dict[str, object]]:
    return _INDEX.search(query, k=k)


def llm_assisted_candidates(query: str, k: int = 8, objective: str | None = None) -> List[Dict[str, object]]:
    """Deterministic candidate retrieval to support a future LLM pass.

    This implementation does not fabricate evidence. It returns candidates that have
    a real evidence_id and text in the in-memory index; those must still be resolved
    against the external terms API before a finding is reported.
    """
    if not query and not objective:
        return []
    combined = " ".join(filter(None, [query, objective]))
    return retrieve_candidates(combined, k=k)
