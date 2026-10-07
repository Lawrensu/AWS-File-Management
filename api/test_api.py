"""Tests for workstream C. FakeStore only; engine.llm is stubbed, never called for real."""

from __future__ import annotations

import json

import pymupdf
import pytest
from fastapi.testclient import TestClient

from api import ask as ask_module
from api.main import app
from engine.llm import LLMUnavailable, StreamResult
from engine.testing import FakeStore, make_chunk, make_document

OLD = "0000000000000001"
NEW = "0000000000000002"
ENG = "0000000000000003"


@pytest.fixture
def store() -> FakeStore:
    s = FakeStore()
    s.upsert_document(make_document(OLD, title="Pekeliling Bil. 2/2022", status="superseded",
                                    superseded_by=NEW, year=2022))
    s.upsert_document(make_document(NEW, title="Pekeliling Bil. 3/2024"))
    s.upsert_document(make_document(ENG, title="Leave Guideline 2024", lang="en",
                                    department="Bahagian Sumber Manusia", doc_type="guideline"))
    s.upsert_chunks([
        make_chunk(OLD, 1, 0, text="Kadar elaun perjalanan kontraktor RM0.50 sekilometer."),
        make_chunk(NEW, 1, 0, text="Kadar elaun perjalanan kontraktor RM0.70 sekilometer."),
        make_chunk(ENG, 1, 0, text="Annual leave applications need approval.", lang="en"),
    ])
    return s


@pytest.fixture
def client(store, monkeypatch) -> TestClient:
    monkeypatch.setenv("EMBED_FAKE", "1")
    app.state.store = store
    yield TestClient(app)
    app.state.store = None


def fake_stream(text_parts, provider="groq", seen=None):
    def _stream(system, user, *, role, max_tokens):
        assert role == "answer"
        if seen is not None:
            seen.append(user)
        return StreamResult(provider, "test-model", iter(text_parts))
    return _stream


# --- C1 -----------------------------------------------------------------------------------


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "documents": 3, "chunks": 3}


def test_health_without_store():
    app.state.store = None
    r = TestClient(app).get("/health")
    assert r.json() == {"ok": True, "documents": 0, "chunks": 0}


def test_no_store_is_503():
    app.state.store = None
    r = TestClient(app).post("/search", json={"query": "elaun"})
    assert r.status_code == 503
    assert r.json() == {"error": "index not ready"}


def test_validation_error_shape(client):
    r = client.post("/search", json={"query": "elaun", "top_k": 500})
    assert r.status_code == 422
    assert set(r.json()) == {"error"}
    assert r.json()["error"].startswith("top_k:")


def test_malformed_json_is_422_with_error_key(client):
    r = client.post("/search", content="{bad json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json() == {"error": "body: JSON decode error"}
    r = client.post("/search", json={"q": "x"})
    assert r.status_code == 422 and r.json() == {"error": "query: Field required"}


# --- C2 -----------------------------------------------------------------------------------


def test_search_returns_contract_shape(client):
    r = client.post("/search", json={"query": "elaun perjalanan kontraktor"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results[0]["doc_id"] == NEW  # superseded one is demoted below the current one
    assert {x["doc_id"] for x in results} >= {OLD, NEW}
    assert set(results[0]) == {
        "chunk_id", "doc_id", "title", "page", "snippet", "score", "doc_type",
        "department", "status", "superseded_by", "lang",
    }


def test_search_department_filter(client):
    body = {"query": "leave elaun", "filters": {"department": "Jabatan Kewangan"}}
    ids = {x["doc_id"] for x in client.post("/search", json=body).json()["results"]}
    assert ENG not in ids


def test_search_survives_embedding_failure(client, monkeypatch):
    monkeypatch.setenv("EMBED_FAKE", "0")

    def boom(*a, **k):
        raise RuntimeError("no bedrock")

    monkeypatch.setattr("api.deps.embed_texts", boom)
    r = client.post("/search", json={"query": "elaun"})
    assert r.status_code == 200 and r.json()["results"]


# --- C3 -----------------------------------------------------------------------------------


def test_ask_maps_citations(client, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(ask_module, "preferred_provider", lambda role: "groq")
    monkeypatch.setattr(ask_module, "stream", fake_stream(
        ["Kadar ialah RM0.70 [1]. ", "Kadar lama RM0.50 telah dibatalkan [2] [1] [9]."], seen=seen))
    r = client.post("/ask", json={"question": "Berapakah kadar elaun perjalanan kontraktor?"})
    assert r.status_code == 200
    assert r.headers["x-rujuk-provider"] == "groq"
    body = r.json()
    assert body["language"] == "ms" and body["not_found"] is False
    assert [c["n"] for c in body["citations"]] == [1, 2]  # first appearance, 9 dropped
    assert body["citations"][0]["doc_id"] == NEW
    assert body["citations"][1]["status"] == "superseded"
    assert "SUPERSEDED by Pekeliling Bil. 3/2024" in seen[0]
    assert set(body) == {"answer", "language", "confidence", "citations", "not_found"}


def test_ask_prompt_names_the_answer_language(client, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(ask_module, "preferred_provider", lambda role: "groq")
    monkeypatch.setattr(ask_module, "stream", fake_stream(["RM0.70 [1]."], seen=seen))
    client.post("/ask", json={"question": "Do annual leave applications need approval?"})
    client.post("/ask", json={"question": "Berapakah kadar elaun perjalanan kontraktor?"})
    assert seen[0].rstrip().endswith("Answer in English.")
    assert seen[1].rstrip().endswith("Answer in Bahasa Malaysia.")


def test_system_prompt_asks_to_flag_superseded_values():
    assert "SUPERSEDED" in ask_module.SYSTEM
    assert "different value" in ask_module.SYSTEM


def test_ask_chunk_budget_follows_provider(client, monkeypatch):
    for provider, k in (("bedrock", 8), ("groq", 5)):
        captured = {}

        def fake_search(store, q, vec, filters, top_k, _c=captured):
            _c["top_k"] = top_k
            return []

        monkeypatch.setattr(ask_module, "preferred_provider", lambda role, p=provider: p)
        monkeypatch.setattr(ask_module, "hybrid_search", fake_search)
        client.post("/ask", json={"question": "anything"})
        assert captured["top_k"] == k


def test_ask_not_found(client, monkeypatch):
    monkeypatch.setattr(ask_module, "preferred_provider", lambda role: "groq")
    monkeypatch.setattr(ask_module, "stream", fake_stream(["Not found in the available documents."]))
    body = client.post("/ask", json={"question": "What is the annual leave salary?"}).json()
    assert body["not_found"] is True
    assert body["confidence"] == "low" and body["citations"] == []


def test_ask_no_hits_skips_model(client, monkeypatch):
    def never(*a, **k):
        raise AssertionError("model must not be called")

    monkeypatch.setattr(ask_module, "stream", never)
    body = client.post("/ask", json={"question": "Berapakah gaji Perdana Menteri xyzzy?"}).json()
    assert body["not_found"] is True
    assert body["answer"] == "Tidak dijumpai dalam dokumen yang tersedia."


def test_ask_llm_unavailable_is_503(client, monkeypatch):
    def unavailable(*a, **k):
        raise LLMUnavailable("no provider")

    monkeypatch.setattr(ask_module, "stream", unavailable)
    r = client.post("/ask", json={"question": "kadar elaun perjalanan"})
    assert r.status_code == 503
    assert r.json()["error"].startswith("answer model unavailable")


def test_ask_streams_sse(client, monkeypatch):
    monkeypatch.setattr(ask_module, "preferred_provider", lambda role: "bedrock")
    monkeypatch.setattr(ask_module, "stream", fake_stream(["RM0.70 ", "[1]."], "bedrock"))
    r = client.post("/ask", json={"question": "kadar elaun perjalanan", "stream": True})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert [e["type"] for e in events] == ["token", "token", "done"]
    assert events[-1]["answer"]["citations"][0]["n"] == 1


def test_question_language():
    assert ask_module.question_language("Berapakah kadar elaun?") == "ms"
    assert ask_module.question_language("What is the travel allowance rate?") == "en"


# --- C4 -----------------------------------------------------------------------------------


@pytest.fixture
def pdf_doc(store, tmp_path):
    path = tmp_path / "doc.pdf"
    pdf = pymupdf.open()
    for i in range(2):
        pdf.new_page().insert_text((72, 100), f"Kadar elaun perjalanan halaman {i + 1}.")
    pdf.save(path)
    doc_id = "00000000000000aa"
    store.upsert_document(make_document(doc_id, source_path=str(path), page_count=2))
    store.upsert_chunks([make_chunk(doc_id, 1, 0, text="Kadar elaun perjalanan halaman 1.")])
    return doc_id


def test_list_and_get_documents(client):
    docs = client.get("/documents").json()["documents"]
    assert len(docs) == 3
    detail = client.get(f"/documents/{NEW}").json()
    assert detail["doc_id"] == NEW
    assert detail["chunks"] and "embedding" not in detail["chunks"][0]


def test_unknown_document_404(client):
    r = client.get("/documents/ffffffffffffffff")
    assert r.status_code == 404 and "error" in r.json()


def test_page_png_with_highlight(client, pdf_doc):
    plain = client.get(f"/documents/{pdf_doc}/pages/1.png")
    lit = client.get(f"/documents/{pdf_doc}/pages/1.png?highlight={pdf_doc}:1:0")
    assert plain.status_code == lit.status_code == 200
    assert lit.headers["content-type"] == "image/png"
    assert lit.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert lit.content != plain.content  # the yellow box changed the pixels


def test_page_png_out_of_range(client, pdf_doc):
    assert client.get(f"/documents/{pdf_doc}/pages/3.png").status_code == 404
    assert client.get(f"/documents/{pdf_doc}/pages/0.png").status_code == 404


# --- C5 -----------------------------------------------------------------------------------


def test_upload_rejects_bad_files(client):
    assert client.post("/documents/upload").status_code == 400
    r = client.post("/documents/upload", files={"file": ("a.txt", b"hi", "text/plain")})
    assert r.status_code == 400
    r = client.post("/documents/upload", files={"file": ("a.pdf", b"", "application/pdf")})
    assert r.status_code == 400


def test_upload_then_search(client, monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr("engine.ingest.tagger.complete", _no_llm, raising=False)
    pdf = pymupdf.open()
    # Over 50 characters, or extract_pages marks the page as scanned and skips it.
    pdf.new_page().insert_text(
        (72, 100), "Garis panduan tempahan bilik mesyuarat zebra untuk semua pegawai jabatan."
    )
    data = pdf.tobytes()

    r = client.post("/documents/upload", files={"file": ("bilik.pdf", data, "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"doc_id", "title", "pages", "chunks", "status", "department"}
    assert body["pages"] == 1 and body["chunks"] >= 1

    hits = client.post("/search", json={"query": "zebra"}).json()["results"]
    assert hits and hits[0]["doc_id"] == body["doc_id"]


def _no_llm(*a, **k):
    raise LLMUnavailable("stubbed")
