from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from engine.index.store import SqliteStore
from engine.testing import make_chunk, make_document

DOC = "a1b2c3d4e5f60718"
OTHER = "0f1e2d3c4b5a6978"
WORDS = [
    "elaun",
    "cuti",
    "perolehan",
    "latihan",
    "disiplin",
    "bajet",
    "mesyuarat",
    "rekod",
    "siber",
    "kontraktor",
    "tuntutan",
    "sebut",
    "harga",
    "kelulusan",
    "audit",
    "aset",
    "kenderaan",
    "lebih",
    "masa",
    "pencen",
]


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(tmp_path / "index.sqlite")
    yield s
    s.close()


def twenty_chunks() -> list[dict]:
    # One distinctive word per chunk, shared filler so BM25 has common terms too.
    return [
        make_chunk(
            DOC,
            page=i // 4 + 1,
            n=i % 4,
            seed=i,
            text=f"Pekeliling ini menerangkan {w} bagi semua jabatan.",
        )
        for i, w in enumerate(WORDS)
    ]


def test_twenty_chunks_both_searches_return_expected_ids(store):
    chunks = twenty_chunks()
    store.upsert_document(make_document(DOC))
    store.upsert_chunks(chunks)

    assert store.count() == (1, 20)
    for i in (0, 7, 19):
        assert store.bm25_search(WORDS[i], 5)[0][0] == chunks[i]["chunk_id"]
        cid, score = store.vector_search(np.array(chunks[i]["embedding"]), 5)[0]
        assert cid == chunks[i]["chunk_id"]
        assert score == pytest.approx(1.0, abs=1e-5)


def test_search_results_are_best_first_and_capped_at_k(store):
    store.upsert_chunks(twenty_chunks())
    hits = store.vector_search(np.ones(1024), 7)
    assert len(hits) == 7
    assert [s for _, s in hits] == sorted((s for _, s in hits), reverse=True)
    assert len(store.bm25_search("pekeliling jabatan", 3)) == 3


def test_empty_store_returns_nothing(store):
    assert store.count() == (0, 0)
    assert store.list_documents() == []
    assert store.bm25_search("elaun", 10) == []
    assert store.vector_search(np.ones(1024), 10) == []
    assert store.get_document(DOC) is None
    assert store.get_chunk(f"{DOC}:1:0") is None
    assert store.chunks_for_document(DOC) == []


def test_one_chunk_corpus_still_gets_keyword_hits(store):
    # rank_bm25's own idf scores this at or below zero; the Lucene idf keeps it positive.
    store.upsert_chunks([make_chunk(DOC, text="Kadar elaun perjalanan RM0.70 sekilometer.")])
    hits = store.bm25_search("elaun", 5)
    assert [cid for cid, _ in hits] == [f"{DOC}:1:0"]
    assert hits[0][1] > 0


def test_bm25_drops_chunks_that_do_not_match(store):
    store.upsert_chunks(twenty_chunks())
    assert store.bm25_search("zzzz", 10) == []
    assert store.bm25_search("", 10) == []
    assert [cid for cid, _ in store.bm25_search("audit", 10)] == [f"{DOC}:4:2"]


def test_works_from_a_second_thread(store):
    # FastAPI opens the store in the lifespan and serves requests from a thread pool.
    def work() -> tuple[int, int]:
        store.upsert_document(make_document(DOC))
        store.upsert_chunks(twenty_chunks())
        store.bm25_search("elaun", 3)
        return store.count()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert pool.submit(work).result() == (1, 20)
        assert pool.submit(store.bm25_search, "cuti", 3).result()[0][0] == f"{DOC}:1:1"


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "index.sqlite"
    first = SqliteStore(path)
    first.upsert_document(make_document(DOC))
    first.upsert_chunks(twenty_chunks())
    first.close()

    again = SqliteStore(path)
    try:
        assert again.count() == (1, 20)
        assert again.get_document(DOC)["title"] == make_document(DOC)["title"]
        assert again.bm25_search("bajet", 1)[0][0] == f"{DOC}:2:1"
        assert (
            again.vector_search(np.array(twenty_chunks()[5]["embedding"]), 1)[0][0] == f"{DOC}:2:1"
        )
    finally:
        again.close()


def test_sees_writes_from_another_connection(tmp_path):
    # The ingest CLI writes from its own process while the API keeps its store open.
    path = tmp_path / "index.sqlite"
    api, cli = SqliteStore(path), SqliteStore(path)
    try:
        assert api.count() == (0, 0)
        cli.upsert_document(make_document(DOC))
        cli.upsert_chunks(twenty_chunks())
        assert api.count() == (1, 20)
        assert api.get_document(DOC) is not None
        assert api.bm25_search("pencen", 1)[0][0] == f"{DOC}:5:3"
    finally:
        api.close()
        cli.close()


def test_creates_missing_parent_folder(tmp_path):
    path = tmp_path / "data" / "nested" / "index.sqlite"
    s = SqliteStore(path)
    try:
        assert path.exists()
    finally:
        s.close()


def test_upsert_chunks_replaces_the_documents_chunks(store):
    store.upsert_chunks(twenty_chunks())
    store.upsert_chunks([make_chunk(OTHER, text="Dokumen lain tentang elaun.")])
    replacement = make_chunk(DOC, text="Versi baharu tentang cuti rehat.", seed=99)
    store.upsert_chunks([replacement])

    assert store.count() == (0, 2)
    assert [c["chunk_id"] for c in store.chunks_for_document(DOC)] == [f"{DOC}:1:0"]
    assert store.get_chunk(f"{DOC}:3:2") is None
    assert [cid for cid, _ in store.bm25_search("elaun", 10)] == [f"{OTHER}:1:0"]
    assert store.vector_search(np.array(replacement["embedding"]), 1)[0][0] == f"{DOC}:1:0"


def test_upsert_document_updates_in_place(store):
    store.upsert_document(make_document(DOC))
    store.upsert_document(make_document(OTHER, title="Lain"))
    store.upsert_document(make_document(DOC, status="superseded", superseded_by=OTHER))

    assert store.get_document(DOC)["status"] == "superseded"
    assert [d["doc_id"] for d in store.list_documents()] == [DOC, OTHER]


def test_reads_return_copies_without_embedding(store):
    store.upsert_document(make_document(DOC))
    store.upsert_chunks([make_chunk(DOC)])

    store.get_document(DOC)["status"] = "superseded"
    store.list_documents()[0]["title"] = "changed"
    chunk = store.get_chunk(f"{DOC}:1:0")
    chunk["text"] = "changed"

    assert "embedding" not in chunk
    assert "embedding" not in store.chunks_for_document(DOC)[0]
    assert store.get_document(DOC)["status"] == "current"
    assert store.get_document(DOC)["title"] != "changed"
    assert store.get_chunk(f"{DOC}:1:0")["text"] != "changed"


def test_chunks_for_document_in_page_order(store):
    store.upsert_chunks(
        [
            make_chunk(DOC, page=2, n=1),
            make_chunk(DOC, page=1, n=0),
            make_chunk(DOC, page=2, n=0),
            make_chunk(DOC, page=10, n=0),
        ]
    )
    assert [c["chunk_id"] for c in store.chunks_for_document(DOC)] == [
        f"{DOC}:1:0",
        f"{DOC}:2:0",
        f"{DOC}:2:1",
        f"{DOC}:10:0",
    ]


def test_null_embedding_is_keyword_searchable_only(store):
    store.upsert_chunks(
        [
            make_chunk(DOC, n=0, text="imbasan tanpa vektor", embedding=None),
            make_chunk(DOC, n=1, text="teks biasa", seed=1),
        ]
    )
    assert store.bm25_search("imbasan", 5)[0][0] == f"{DOC}:1:0"
    assert [cid for cid, _ in store.vector_search(np.ones(1024), 5)] == [f"{DOC}:1:1"]


def test_accepts_numpy_values_from_ingest(store):
    chunk = make_chunk(DOC, page=np.int64(3), bbox=np.array([1.0, 2.0, 3.0, 4.0]))
    chunk["embedding"] = np.asarray(chunk["embedding"], dtype=np.float32)
    store.upsert_chunks([chunk])
    assert store.get_chunk(f"{DOC}:3:0")["page"] == 3
    assert store.get_chunk(f"{DOC}:3:0")["bbox"] == [1.0, 2.0, 3.0, 4.0]


def test_rejects_chunk_without_page(store):
    with pytest.raises(ValueError, match="page"):
        store.upsert_chunks([make_chunk(DOC, page=None)])
    with pytest.raises(ValueError, match="page"):
        store.upsert_chunks([make_chunk(DOC, page=0)])
    assert store.count() == (0, 0)


def test_rejects_mismatched_dimensions(store):
    store.upsert_chunks([make_chunk(DOC, dim=8, seed=1)])
    with pytest.raises(ValueError, match="dimension"):
        store.vector_search(np.ones(4), 5)
    with pytest.raises(ValueError, match="dimension"):
        store.upsert_chunks([make_chunk(OTHER, dim=4, seed=2)])
