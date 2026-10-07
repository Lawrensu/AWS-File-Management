from __future__ import annotations

import numpy as np
import pytest

from engine.index.hybrid import SUPERSEDED_RANK_OFFSET, Filters, hybrid_search, rrf
from engine.testing import FakeStore, make_chunk, make_document

RESULT_KEYS = {
    "chunk_id", "doc_id", "title", "page", "snippet", "score", "doc_type", "department",
    "status", "superseded_by", "lang",
}  # fmt: skip


def doc_id(i: int) -> str:
    return f"{i:016x}"


class RankedStore(FakeStore):
    """FakeStore whose searches return fixed rankings, so a test controls ranks exactly."""

    def __init__(self, bm25: list[str], vector: list[str]) -> None:
        super().__init__()
        self.bm25, self.vector = bm25, vector
        self.asked: list[int] = []
        self.vector_calls = 0

    def bm25_search(self, query: str, k: int) -> list[tuple[str, float]]:
        self.asked.append(k)
        return [(cid, float(100 - i)) for i, cid in enumerate(self.bm25[:k])]

    def vector_search(self, query_vec: np.ndarray, k: int) -> list[tuple[str, float]]:
        self.vector_calls += 1
        return [(cid, 1.0 - i / 1000) for i, cid in enumerate(self.vector[:k])]


def add(store: FakeStore, i: int, text: str = "teks", **doc_fields) -> str:
    store.upsert_document(make_document(doc_id(i), title=f"Dokumen {i}", **doc_fields))
    chunk = make_chunk(doc_id(i), text=text, seed=i)
    store.upsert_chunks([chunk])
    return chunk["chunk_id"]


def ids(results: list[dict]) -> list[str]:
    return [r["chunk_id"] for r in results]


# rrf


def test_rrf_symmetric_rankings_give_equal_scores():
    scores = rrf([["a", "b"], ["b", "a"]])
    assert scores["a"] == pytest.approx(scores["b"])
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)


def test_rrf_agreement_beats_disagreement():
    assert rrf([["a"], ["a"]])["a"] > rrf([["a"], ["b"]])["a"]


def test_rrf_demotion_is_a_rank_offset():
    scores = rrf([["a", "b"]], demoted={"a"})
    assert scores["a"] == pytest.approx(1 / (60 + 1 + SUPERSEDED_RANK_OFFSET))
    assert scores["b"] == pytest.approx(1 / 62)


# superseded documents


def superseded_setup() -> tuple[RankedStore, str, str]:
    # OLD is raw #1 in both lists, NEW (its replacement) raw #2, then 28 other chunks.
    store = RankedStore([], [])
    old = add(store, 1, status="superseded", superseded_by=doc_id(2))
    new = add(store, 2)
    others = [add(store, 10 + i) for i in range(28)]
    store.bm25 = store.vector = [old, new, *others]
    return store, old, new


def test_superseded_chunk_stays_in_top_10_below_its_replacement():
    store, old, new = superseded_setup()
    results = ids(hybrid_search(store, "elaun", np.ones(4), Filters(), top_k=10))
    assert new in results and old in results
    assert results.index(new) < results.index(old) < 10


def test_include_superseded_restores_it_to_the_top():
    store, old, new = superseded_setup()
    results = hybrid_search(store, "elaun", np.ones(4), Filters(include_superseded=True))
    assert ids(results)[:2] == [old, new]
    assert results[0]["status"] == "superseded"
    assert results[0]["superseded_by"] == doc_id(2)


# filters


def department_setup() -> tuple[FakeStore, str, str, str]:
    store = FakeStore()
    kew = add(store, 1, "elaun kewangan", department="Jabatan Kewangan")
    per = add(store, 2, "elaun perolehan", department="Jabatan Perolehan", doc_type="sop")
    umum = add(store, 3, "elaun umum", department="Umum")
    return store, kew, per, umum


def test_department_filter_keeps_that_department_and_umum():
    store, kew, _per, umum = department_setup()
    results = hybrid_search(store, "elaun", None, Filters(department="Jabatan Kewangan"))
    assert set(ids(results)) == {kew, umum}


@pytest.mark.parametrize("department", [None, "Umum"])
def test_no_department_filter(department):
    store, kew, per, umum = department_setup()
    results = hybrid_search(store, "elaun", None, Filters(department=department))
    assert set(ids(results)) == {kew, per, umum}


def test_doc_type_filter():
    store, _, per, _ = department_setup()
    assert ids(hybrid_search(store, "elaun", None, Filters(doc_type="sop"))) == [per]


def test_filtered_search_uses_every_chunk_as_the_pool():
    store = RankedStore([], [])
    chunks = [add(store, i) for i in range(5)]
    store.bm25 = store.vector = chunks
    hybrid_search(store, "q", np.ones(4), Filters())
    hybrid_search(store, "q", np.ones(4), Filters(department="Jabatan Kewangan"))
    assert store.asked == [200, 200]  # 5 chunks: the 200 floor already covers them all

    many = RankedStore([], [])
    for i in range(250):
        add(many, i)
    hybrid_search(many, "q", np.ones(4), Filters())
    hybrid_search(many, "q", np.ones(4), Filters(doc_type="circular"))
    assert many.asked == [200, 250]


# query_vec=None and result shape


def test_query_vec_none_is_bm25_only():
    store = RankedStore([], [])
    a, b = add(store, 1), add(store, 2)
    store.bm25, store.vector = [a], [b]
    results = hybrid_search(store, "elaun", None, Filters())
    assert ids(results) == [a]
    assert store.vector_calls == 0


def test_results_match_search_result_contract():
    store = FakeStore()
    long_text = "Kadar elaun perjalanan kontraktor.\n\n" + "perkataan " * 100
    cid = add(store, 1, long_text, department="Jabatan Kewangan")
    store.upsert_chunks([make_chunk(doc_id(1), page=4, text=long_text, lang="en")])

    [result] = hybrid_search(store, "elaun", None, Filters())
    assert set(result) == RESULT_KEYS
    assert result["chunk_id"] != cid and result["page"] == 4
    assert result["title"] == "Dokumen 1"
    assert result["lang"] == "en"
    assert result["department"] == "Jabatan Kewangan"
    assert result["status"] == "current" and result["superseded_by"] is None
    assert isinstance(result["score"], float) and result["score"] > 0
    assert len(result["snippet"]) <= 300
    assert result["snippet"].startswith("Kadar elaun perjalanan kontraktor. perkataan")


def test_top_k_and_ordering():
    store = RankedStore([], [])
    chunks = [add(store, i) for i in range(30)]
    store.bm25 = store.vector = chunks
    results = hybrid_search(store, "q", np.ones(4), Filters(), top_k=5)
    assert ids(results) == chunks[:5]
    assert [r["score"] for r in results] == sorted((r["score"] for r in results), reverse=True)
    assert hybrid_search(store, "q", np.ones(4), Filters(), top_k=0) == []


def test_chunk_without_its_document_is_skipped():
    # Ingest writes the document and its chunks in two commits; a search can land between.
    store = FakeStore()
    orphan = make_chunk(doc_id(9), text="elaun tanpa dokumen")
    store.upsert_chunks([orphan])
    kept = add(store, 1, "elaun dengan dokumen")
    assert ids(hybrid_search(store, "elaun", None, Filters())) == [kept]
