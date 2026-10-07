"""B2. Hybrid search: BM25 + vector, fused with Reciprocal Rank Fusion.

Returns dicts shaped like SearchResult in contracts/api.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from langdetect import DetectorFactory, LangDetectException, detect_langs

from engine.index.store import Chunk, Document, IndexStore

DetectorFactory.seed = 0

RRF_K = 60
# Superseded chunks are scored as if they sat this many places lower in every list. A score
# multiplier cannot do this job: RRF scores are so close together that x0.3 ranks a
# superseded chunk below every other candidate, and the badge never shows.
SUPERSEDED_RANK_OFFSET = 5
# Keyword search cannot match a chunk written in another language, and when the vector list
# covers most of the corpus every keyword hit collects two votes. A cross-language answer
# that only the vectors find then loses to any keyword hit. So for a chunk not in the
# query's language, its missing keyword rank is taken as its vector rank plus this offset.
# On the seed corpus with simulated vectors this lifted recall@5 from 0.70 to 1.00 when the
# vectors rank the answer in their top 3, without costing same-language questions their
# first place. Tune at the 2:30 eval with real vectors.
CROSS_LANGUAGE_OFFSET = 5
CANDIDATE_POOL = 200
SNIPPET_CHARS = 300
NO_DEPARTMENT = "Umum"


@dataclass
class Filters:
    department: str | None = None
    doc_type: str | None = None
    include_superseded: bool = False


def rrf(
    rankings: list[list[str]], k: int = RRF_K, demoted: set[str] | frozenset[str] = frozenset()
) -> dict[str, float]:
    """score(id) = sum over rankings of 1 / (k + rank + offset), rank from 1.

    offset is SUPERSEDED_RANK_OFFSET for ids in demoted, else 0.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, 1):
            scores[cid] = scores.get(cid, 0.0) + _term(rank, cid in demoted, k)
    return scores


def query_language(query: str) -> str | None:
    """Return "ms" or "en" when langdetect is at least 90% sure, else None.

    Two- and three-word queries often come back as Tagalog, Polish or Romanian, so only a
    confident answer counts. langdetect reports Malay as "id" (Indonesian).
    """
    try:
        best = detect_langs(query)[0]
    except LangDetectException:
        return None
    return {"ms": "ms", "id": "ms", "en": "en"}.get(best.lang) if best.prob >= 0.9 else None


def hybrid_search(
    store: IndexStore,
    query: str,
    query_vec: np.ndarray | None,
    filters: Filters,
    top_k: int = 10,
) -> list[dict]:
    """query_vec=None runs BM25 only (embedding failed, or EMBED_FAKE).

    With vectors and a query language langdetect is sure of, chunks in another language get
    a keyword rank imputed from their vector rank (see CROSS_LANGUAGE_OFFSET).
    """
    if top_k <= 0:
        return []
    filtered = _department_filter(filters) is not None or filters.doc_type is not None
    pool = max(CANDIDATE_POOL, store.count()[1]) if filtered else CANDIDATE_POOL

    rankings = [[cid for cid, _ in store.bm25_search(query, pool)]]
    if query_vec is not None:
        rankings.append([cid for cid, _ in store.vector_search(query_vec, pool)])

    candidates: dict[str, tuple[Chunk, Document]] = {}
    docs: dict[str, Document | None] = {}
    for cid in dict.fromkeys(cid for ranking in rankings for cid in ranking):
        chunk = store.get_chunk(cid)
        if chunk is None:
            continue
        if chunk["doc_id"] not in docs:
            docs[chunk["doc_id"]] = store.get_document(chunk["doc_id"])
        doc = docs[chunk["doc_id"]]
        # A chunk can briefly exist without its document: ingest commits them separately.
        if doc is not None and _passes(doc, filters):
            candidates[cid] = (chunk, doc)

    # Rank within what the viewer is allowed to see, so filters do not leave rank gaps.
    rankings = [[cid for cid in ranking if cid in candidates] for ranking in rankings]
    demoted = (
        set()
        if filters.include_superseded
        else {cid for cid, (_, doc) in candidates.items() if doc.get("status") == "superseded"}
    )
    scores = rrf(rankings, RRF_K, demoted)
    lang = query_language(query) if len(rankings) == 2 else None
    if lang is not None:
        keyword_rank = {cid: r for r, cid in enumerate(rankings[0], 1)}
        for r, cid in enumerate(rankings[1], 1):
            if candidates[cid][0].get("lang") != lang:
                imputed = r + CROSS_LANGUAGE_OFFSET
                k_rank = min(keyword_rank.get(cid, imputed), imputed)
                scores[cid] = _term(r, cid in demoted) + _term(k_rank, cid in demoted)
    best = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]
    return [_result(*candidates[cid], scores[cid]) for cid in best]


def _term(rank: int, demoted: bool, k: int = RRF_K) -> float:
    return 1.0 / (k + rank + (SUPERSEDED_RANK_OFFSET if demoted else 0))


def _department_filter(filters: Filters) -> str | None:
    if filters.department in (None, NO_DEPARTMENT):
        return None
    return filters.department


def _passes(doc: Document, filters: Filters) -> bool:
    department = _department_filter(filters)
    # "Umum" documents are general and visible from every department.
    if department is not None and doc.get("department") not in (department, NO_DEPARTMENT):
        return False
    return filters.doc_type is None or doc.get("doc_type") == filters.doc_type


def _result(chunk: Chunk, doc: Document, score: float) -> dict:
    return {
        "chunk_id": chunk["chunk_id"],
        "doc_id": chunk["doc_id"],
        "title": doc.get("title") or doc.get("filename"),
        "page": chunk["page"],
        "snippet": " ".join(chunk.get("text", "").split())[:SNIPPET_CHARS],
        "score": score,
        "doc_type": doc.get("doc_type"),
        "department": doc.get("department"),
        "status": doc.get("status", "current"),
        "superseded_by": doc.get("superseded_by"),
        "lang": chunk.get("lang") or doc.get("lang"),
    }
