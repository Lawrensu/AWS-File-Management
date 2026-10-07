"""C4. GET /documents, /documents/{doc_id}, /documents/{doc_id}/pages/{page}.png."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.deps import Store
from engine.index.store import Document, IndexStore

router = APIRouter()

DPI = 110
HIGHLIGHT_CHARS = (120, 60)  # first try, retry
HIGHLIGHT_FILL = (1, 0.85, 0)
HIGHLIGHT_OPACITY = 0.35
REPO_ROOT = Path(__file__).resolve().parents[1]


@router.get("/documents")
def list_documents(store: Store) -> dict:
    return {"documents": store.list_documents()}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, store: Store) -> dict:
    doc = _require_doc(store, doc_id)
    chunks = store.chunks_for_document(doc_id)
    for chunk in chunks:
        chunk.pop("embedding", None)
    chunks.sort(key=lambda c: (c["page"], int(c["chunk_id"].rsplit(":", 1)[1])))
    return {**doc, "chunks": chunks}


@router.get("/documents/{doc_id}/pages/{page}.png")
def page_png(
    doc_id: str, page: int, store: Store, highlight: str | None = None
) -> Response:
    doc = _require_doc(store, doc_id)
    if page < 1 or page > doc["page_count"]:
        raise HTTPException(status_code=404, detail=f"page {page} out of range")
    path = source_file(doc)
    if path is None:
        raise HTTPException(status_code=404, detail="source file not found")

    text = None
    if highlight:
        chunk = store.get_chunk(highlight)
        if chunk and chunk["doc_id"] == doc_id and chunk["page"] == page:
            text = " ".join(chunk["text"].split())

    png = render_page(path, page, text)
    if png is None:
        raise HTTPException(status_code=404, detail=f"page {page} out of range")
    return Response(
        content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"}
    )


def render_page(path: Path, page: int, highlight_text: str | None = None) -> bytes | None:
    """PNG of a 1-indexed page. Highlight is best effort: no hit gives the plain page."""
    with pymupdf.open(path) as pdf:
        if page > pdf.page_count:
            return None
        p = pdf[page - 1]
        if highlight_text:
            for n in HIGHLIGHT_CHARS:
                rects = p.search_for(highlight_text[:n])
                if rects:
                    break
            for rect in rects:
                p.draw_rect(
                    rect, color=None, fill=HIGHLIGHT_FILL, fill_opacity=HIGHLIGHT_OPACITY,
                    overlay=True,
                )
        return p.get_pixmap(dpi=DPI).tobytes("png")


def source_file(doc: Document) -> Path | None:
    """Local file behind a document. Relative paths resolve from cwd, then the repo root."""
    raw = doc.get("source_path")
    if not raw or raw.startswith("s3://"):
        return None  # TODO(C5): fetch from S3 if uploads move there
    path = Path(raw)
    for candidate in (path, REPO_ROOT / path):
        if candidate.is_file():
            return candidate
    return None


def _require_doc(store: IndexStore, doc_id: str) -> Document:
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document {doc_id} not found")
    return doc
