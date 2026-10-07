from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf as fitz
import pytest

import engine.ingest.__main__ as cli
from engine.ingest import pipeline
from engine.ingest.pipeline import ingest_file
from engine.ingest.tagger import fallback
from engine.testing import FakeStore

SCHEMA = Path(__file__).resolve().parents[2] / "contracts" / "document.schema.json"

MALAY = (
    "Pekeliling ini menetapkan kadar elaun perjalanan baharu bagi semua pegawai awam yang "
    "menjalankan tugas rasmi di luar ibu pejabat. Tuntutan elaun perjalanan hendaklah "
    "dikemukakan dalam tempoh tiga puluh hari selepas perjalanan selesai. Setiap tuntutan "
    "mesti disertakan dengan resit asal dan kelulusan ketua jabatan. Kadar elaun perjalanan "
    "bagi kenderaan persendirian ialah tujuh puluh sen sekilometer."
)

TAGS = {
    "title": "Pekeliling Kewangan Bil. 3/2024",
    "doc_type": "circular",
    "department": "Jabatan Kewangan",
    "topics": ["elaun_dan_tuntutan"],
    "year": 2024,
    "lang": "ms",
    "supersedes": [],
    "summary": "Kadar elaun perjalanan baharu.",
}


def _pdf(path: Path, pages: list[str]) -> Path:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page(width=595, height=842)
        if text:
            page.insert_textbox(fitz.Rect(50, 50, 545, 800), text, fontsize=6)
    doc.save(path)
    doc.close()
    return path


class Counter:
    def __init__(self, fn: Any) -> None:
        self.fn, self.calls = fn, []

    def __call__(self, *args: Any) -> Any:
        self.calls.append(args)
        return self.fn(*args)


@pytest.fixture
def stages(monkeypatch: pytest.MonkeyPatch) -> tuple[Counter, Counter]:
    monkeypatch.setenv("EMBED_FAKE", "1")
    tag = Counter(lambda filename, text: dict(TAGS))
    emb = Counter(pipeline.embed_texts)
    monkeypatch.setattr(pipeline, "tag_document", tag)
    monkeypatch.setattr(pipeline, "embed_texts", emb)
    return tag, emb


def test_ingest_two_page_pdf(tmp_path: Path, stages: tuple[Counter, Counter]) -> None:
    path = _pdf(tmp_path / "doc.pdf", [MALAY, ""])
    store = FakeStore()

    result = ingest_file(path, store)

    assert result.skipped is False
    assert result.doc_id == hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    assert result.pages == 2
    assert result.chunks >= 1
    assert result.title == TAGS["title"]
    assert result.department == "Jabatan Kewangan"
    assert result.status == "current"

    chunks = store.chunks_for_document(result.doc_id)
    assert len(chunks) == result.chunks
    for c in chunks:
        assert c["page"] == 1
        assert c["chunk_id"].startswith(result.doc_id + ":")
        assert c["lang"] in {"ms", "en", "mixed"}

    doc = store.get_document(result.doc_id)
    assert doc is not None
    assert doc["has_scanned_pages"] is True
    assert doc["page_count"] == 2
    assert doc["status"] == "current"
    assert doc["lang"] == "ms"
    assert doc["filename"] == "doc.pdf"
    assert "summary" not in doc
    props = json.loads(SCHEMA.read_text(encoding="utf-8"))["properties"]
    assert set(doc) <= set(props)
    assert set(json.loads(SCHEMA.read_text(encoding="utf-8"))["required"]) <= set(doc)


def test_embeddings_present(tmp_path: Path, stages: tuple[Counter, Counter]) -> None:
    store = FakeStore()
    result = ingest_file(_pdf(tmp_path / "doc.pdf", [MALAY]), store)

    stored = [c for c in store._chunks.values() if c["doc_id"] == result.doc_id]
    assert stored and all(len(c["embedding"]) == 1024 for c in stored)
    vec = np.asarray(stored[0]["embedding"])
    assert store.vector_search(vec, 1)[0][0] == stored[0]["chunk_id"]


def test_idempotent(tmp_path: Path, stages: tuple[Counter, Counter]) -> None:
    tag, emb = stages
    path = _pdf(tmp_path / "doc.pdf", [MALAY])
    store = FakeStore()

    first = ingest_file(path, store)
    counts = store.count()
    second = ingest_file(path, store)

    assert second.skipped is True
    assert second.doc_id == first.doc_id
    assert second.chunks == first.chunks
    assert second.pages == first.pages
    assert len(tag.calls) == 1
    assert len(emb.calls) == 1
    assert store.count() == counts


def test_embed_called_once_for_many_chunks(tmp_path: Path, stages: tuple[Counter, Counter]) -> None:
    _, emb = stages
    # 2000 words on one page: too many for a textbox, so write 20 words per line.
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for line in range(100):
        words = " ".join(f"kata{line * 20 + i}" for i in range(20))
        page.insert_text((20, 20 + line * 8), words, fontsize=5)
    path = tmp_path / "long.pdf"
    doc.save(path)
    doc.close()
    store = FakeStore()
    result = ingest_file(path, store)

    assert result.chunks >= 3
    assert len(emb.calls) == 1
    assert len(emb.calls[0][0]) == result.chunks


def test_tagger_fallback_uses_detect_lang(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stages: tuple[Counter, Counter]
) -> None:
    monkeypatch.setattr(pipeline, "tag_document", lambda filename, text: fallback(filename))
    store = FakeStore()
    result = ingest_file(_pdf(tmp_path / "doc.pdf", [MALAY]), store)

    doc = store.get_document(result.doc_id)
    assert doc is not None
    assert doc["lang"] == "ms"
    assert doc["doc_type"] == "other"
    assert doc["title"] == "doc.pdf"


def test_fully_scanned_document_listed_without_chunks(
    tmp_path: Path, stages: tuple[Counter, Counter]
) -> None:
    _, emb = stages
    store = FakeStore()
    result = ingest_file(_pdf(tmp_path / "scan.pdf", ["", ""]), store)

    assert result.chunks == 0
    assert store.count() == (1, 0)
    assert emb.calls == []
    doc = store.get_document(result.doc_id)
    assert doc is not None and doc["has_scanned_pages"] is True


def test_cli_ingests_folder_and_resolves_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stages: tuple[Counter, Counter],
) -> None:
    _pdf(tmp_path / "a.pdf", [MALAY])
    _pdf(tmp_path / "b.pdf", [MALAY + " Tambahan."])
    (tmp_path / "notes.md").write_text("not a pdf", encoding="utf-8")
    resolve = Counter(lambda store: [])
    monkeypatch.setattr(cli, "resolve_supersession", resolve)
    store = FakeStore()

    code = cli.main([str(tmp_path)], store=store)

    assert code == 0
    assert len(resolve.calls) == 1
    assert store.count()[0] == 2
    assert "documents: 2" in capsys.readouterr().out


def test_cli_missing_folder(tmp_path: Path) -> None:
    assert cli.main([str(tmp_path / "nope")], store=FakeStore()) == 2


def test_failed_chunk_write_leaves_no_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stages: tuple[Counter, Counter]
) -> None:
    path = _pdf(tmp_path / "doc.pdf", [MALAY])
    store = FakeStore()
    real_upsert = store.upsert_chunks

    def boom(chunks: list[Any]) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "upsert_chunks", boom)
    with pytest.raises(RuntimeError, match="disk full"):
        ingest_file(path, store)
    assert store.count() == (0, 0)  # no half-ingested document to skip later

    monkeypatch.setattr(store, "upsert_chunks", real_upsert)
    retry = ingest_file(path, store)
    assert retry.skipped is False
    assert retry.chunks >= 1
