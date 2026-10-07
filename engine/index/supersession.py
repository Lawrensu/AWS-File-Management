"""B3. Mark documents that a newer document says it replaces.

Run once after ingest (A6 CLI) and after every upload (C5).
"""

from __future__ import annotations

import re
from pathlib import Path

from rapidfuzz import fuzz, utils

from engine.index.store import Document, IndexStore

MATCH_THRESHOLD = 80
_REF_NUMBER = re.compile(r"(\d+)\s*/\s*(\d{4})")


def resolve_supersession(store: IndexStore) -> list[tuple[str, str]]:
    """Recompute status and superseded_by from every document's "supersedes" list.

    Returns [(old_doc_id, new_doc_id)] for every reference that resolved. Each run starts
    from scratch, so it is idempotent and clears a mark whose reference has disappeared.
    Documents with status "draft" are never touched unless something supersedes them.
    """
    docs = store.list_documents()
    pairs: list[tuple[str, str]] = []
    replaced_by: dict[str, str] = {}
    # Oldest first, so when two documents replace the same one the newest wins.
    for new in sorted(docs, key=lambda d: (_year(d) or 0, d.get("title") or "")):
        for ref in new.get("supersedes") or []:
            old = _best_match(ref, new, docs)
            if old is None:
                continue
            if (old["doc_id"], new["doc_id"]) not in pairs:
                pairs.append((old["doc_id"], new["doc_id"]))
            replaced_by[old["doc_id"]] = new["doc_id"]

    for doc in docs:
        if doc["doc_id"] in replaced_by:
            want = ("superseded", replaced_by[doc["doc_id"]])
        elif doc.get("status") == "superseded":
            want = ("current", None)
        else:
            continue
        if (doc.get("status"), doc.get("superseded_by")) != want:
            doc["status"], doc["superseded_by"] = want
            store.upsert_document(doc)
    return pairs


def _best_match(ref: str, new: Document, docs: list[Document]) -> Document | None:
    number = _number_pattern(ref)
    best, best_score = None, -1.0
    for cand in docs:
        if cand["doc_id"] == new["doc_id"]:
            continue
        old_year, new_year = _year(cand), _year(new)
        if old_year is not None and new_year is not None and old_year >= new_year:
            continue
        names = [n for n in (cand.get("title"), Path(cand.get("filename") or "").stem) if n]
        # Circulars in one series differ only by number, and fuzzy scores barely notice.
        if number is not None and not any(number.search(n) for n in names):
            continue
        score = max(
            (fuzz.partial_ratio(ref, n, processor=utils.default_process) for n in names),
            default=0.0,
        )
        if score >= MATCH_THRESHOLD and score > best_score:
            best, best_score = cand, score
    return best


def _number_pattern(ref: str) -> re.Pattern[str] | None:
    """For "Bil. 2/2022": matches 2/2022, 02/2022 and 2-2022, but not 12/2022."""
    m = _REF_NUMBER.search(ref)
    if m is None:
        return None
    return re.compile(rf"(?<!\d)0*{int(m[1])}\s*[/-]\s*{m[2]}(?!\d)")


def _year(doc: Document) -> int | None:
    try:
        return int(doc["year"]) if doc.get("year") is not None else None
    except (TypeError, ValueError):
        return None
