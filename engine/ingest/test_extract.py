from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

from engine.ingest.extract import Block, Page, extract_pages

SENTENCE = "Kadar elaun perjalanan bagi pegawai kumpulan pengurusan adalah RM0.70 sekilometer."


def _make_pdf(path: Path, pages: list[list[tuple[float, float, str]]]) -> Path:
    doc = fitz.open()
    for inserts in pages:
        page = doc.new_page(width=595, height=842)
        for x, y, text in inserts:
            page.insert_text((x, y), text)
    doc.save(path)
    doc.close()
    return path


def test_two_page_pdf_gives_pages_bboxes_and_scanned_flag(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "t.pdf", [[(72, 72, SENTENCE)], []])

    pages = extract_pages(pdf)

    assert [p.number for p in pages] == [1, 2]
    assert all(isinstance(p, Page) for p in pages)
    assert SENTENCE in pages[0].text
    assert any(
        isinstance(b, Block) and b.bbox[2] > b.bbox[0] and b.bbox[3] > b.bbox[1]
        for b in pages[0].blocks
    )
    assert pages[0].is_scanned is False
    assert pages[1].is_scanned is True
    assert pages[1].blocks == []


def test_blocks_sorted_top_to_bottom(tmp_path: Path) -> None:
    pdf = _make_pdf(
        tmp_path / "t.pdf",
        [[(72, 300, "Lower block written first."), (72, 100, "Upper block written second.")]],
    )

    blocks = extract_pages(pdf)[0].blocks

    assert [b.text for b in blocks] == ["Upper block written second.", "Lower block written first."]
    assert blocks[0].bbox[1] < blocks[1].bbox[1]


def test_page_size(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "t.pdf", [[(72, 72, SENTENCE)]])

    page = extract_pages(pdf)[0]

    assert page.width == 595
    assert page.height == 842


def test_accepts_str_path(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "t.pdf", [[(72, 72, SENTENCE)]])

    assert len(extract_pages(str(pdf))) == 1
