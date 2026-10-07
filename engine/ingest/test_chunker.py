from __future__ import annotations

import pytest

from engine.ingest.chunker import chunk_pages
from engine.ingest.extract import Block, Page

DOC = "a1b2c3d4e5f60718"
KEYS = {"chunk_id", "doc_id", "page", "bbox", "heading", "text", "lang", "source", "embedding"}


def _page(number: int, *texts: str) -> Page:
    blocks = [Block(t, (72.0, 100.0 + 50 * i, 540.0, 140.0 + 50 * i)) for i, t in enumerate(texts)]
    text = "\n".join(b.text for b in blocks)
    return Page(number, text, blocks, len(text.strip()) < 50, 595.0, 842.0)


def _words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_short_page_gives_one_chunk() -> None:
    page = _page(1, _words(30))
    chunks = chunk_pages(DOC, [page])
    assert len(chunks) == 1
    c = chunks[0]
    assert set(c) == KEYS
    assert c["chunk_id"] == f"{DOC}:1:0"
    assert c["doc_id"] == DOC
    assert c["page"] == 1
    assert c["bbox"] == list(page.blocks[0].bbox)
    assert c["source"] == "native"
    assert c["lang"] == "en"
    assert c["embedding"] is None
    assert c["text"] == _words(30)


def test_long_page_gives_overlapping_windows() -> None:
    blocks = [_words(500, f"b{i}_") for i in range(4)]  # 2000 words over 4 blocks
    page = _page(1, *blocks)
    chunks = chunk_pages(DOC, [page])
    assert len(chunks) == 3
    w = [c["text"].split() for c in chunks]
    assert [len(x) for x in w] == [800, 800, 600]
    assert w[0][-100:] == w[1][:100]
    assert w[1][-100:] == w[2][:100]
    assert w[2][-1] == "b3_499"
    # chunk 1 starts at word 700, inside block 1; chunk 2 at word 1400, inside block 2
    assert chunks[1]["bbox"] == list(page.blocks[1].bbox)
    assert chunks[2]["bbox"] == list(page.blocks[2].bbox)
    assert [c["chunk_id"] for c in chunks] == [f"{DOC}:1:{n}" for n in range(3)]


def test_pages_never_merge_and_empty_page_skipped() -> None:
    pages = [_page(1, _words(900)), _page(2), _page(3, _words(40, "p3_"))]
    chunks = chunk_pages(DOC, pages)
    assert {c["page"] for c in chunks} == {1, 3}
    assert all(c["page"] >= 1 and c["text"] for c in chunks)
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
    assert f"{DOC}:3:0" in ids
    assert all(not t.startswith("p3_") for c in chunks if c["page"] == 1 for t in c["text"].split())


def test_heading_picked_up() -> None:
    page = _page(1, "2. KADAR ELAUN", "Kadar elaun perjalanan bagi pegawai adalah seperti berikut.")
    chunks = chunk_pages(DOC, [page])
    assert chunks[0]["heading"] == "2. KADAR ELAUN"


def test_heading_rules() -> None:
    body = _page(1, "Kadar elaun perjalanan bagi pegawai kumpulan pengurusan adalah baharu.")
    assert chunk_pages(DOC, [body])[0]["heading"] is None

    year = _page(1, "2024 adalah tahun", "Badan teks biasa di sini.")
    assert chunk_pages(DOC, [year])[0]["heading"] is None

    for heading in ("BAHAGIAN I", "2.1 Skop", "PENGENALAN"):
        page = _page(1, heading, "Badan teks biasa di sini untuk ujian.")
        assert chunk_pages(DOC, [page])[0]["heading"] == heading


def test_heading_carries_over_from_earlier_page() -> None:
    pages = [
        _page(1, "3. TUNTUTAN", "Teks badan."),
        _page(2, "Sambungan teks badan dari muka lepas."),
    ]
    chunks = chunk_pages(DOC, pages)
    assert chunks[1]["page"] == 2
    assert chunks[1]["heading"] == "3. TUNTUTAN"


def test_bad_overlap_raises() -> None:
    with pytest.raises(ValueError):
        chunk_pages(DOC, [_page(1, "x")], max_tokens=10, overlap=10)
