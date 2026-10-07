"""A6. One file into the index: extract, chunk, detect language, tag, embed, upsert."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from engine.index.store import Document, IndexStore
from engine.ingest.chunker import chunk_pages
from engine.ingest.embed import embed_texts
from engine.ingest.extract import extract_pages
from engine.ingest.keywords import detect_lang, extract_keywords
from engine.ingest.tagger import tag_document

TAG_PAGES = 3  # the tagger reads the first pages only


class IngestResult(BaseModel):
    """Mirrors the POST /documents/upload response in contracts/api.md, plus skipped."""

    doc_id: str
    title: str
    pages: int
    chunks: int
    status: str
    department: str
    skipped: bool = False  # True when doc_id was already in the store


def ingest_file(path: str | Path, store: IndexStore) -> IngestResult:
    """Ingest one PDF. Idempotent on doc_id = sha256(file bytes)[:16]."""
    path = Path(path)
    doc_id = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

    existing = store.get_document(doc_id)
    if existing is not None:
        return IngestResult(
            doc_id=doc_id,
            title=existing["title"],
            pages=existing["page_count"],
            chunks=len(store.chunks_for_document(doc_id)),
            status=existing["status"],
            department=existing["department"],
            skipped=True,
        )

    pages = extract_pages(path)
    # TODO(A7): scanned pages are skipped; OCR them with Textract and chunk with source="textract".
    text_pages = [p for p in pages if not p.is_scanned]
    chunks = chunk_pages(doc_id, text_pages)
    for chunk in chunks:
        chunk["lang"] = detect_lang(chunk["text"])  # local langdetect, not a model call

    head = "\n".join(p.text for p in pages[:TAG_PAGES])
    tags = tag_document(path.name, head)  # once per document

    full_text = "\n".join(p.text for p in text_pages)
    lang = tags["lang"] or detect_lang(full_text)
    # TODO(A): add "summary" to contracts/document.schema.json, then store tags["summary"].
    doc: Document = {
        "doc_id": doc_id,
        "title": tags["title"],
        "filename": path.name,
        "source_path": path.as_posix(),
        "doc_type": tags["doc_type"],
        "department": tags["department"],
        "topics": tags["topics"],
        "year": tags["year"],
        "lang": lang,
        "status": "current",
        "supersedes": tags["supersedes"],
        "superseded_by": None,
        "keywords": extract_keywords(full_text, lang),
        "page_count": len(pages),
        "has_scanned_pages": any(p.is_scanned for p in pages),
        "ingested_at": datetime.now(UTC).isoformat(),
    }

    if chunks:
        vecs = embed_texts([c["text"] for c in chunks])  # one batch per document
        for chunk, vec in zip(chunks, vecs):
            chunk["embedding"] = vec

    # Chunks first, document last: the document row marks a finished ingest, so a crash
    # between the two writes leaves no document and the next run retries the file.
    if chunks:
        store.upsert_chunks(chunks)
    store.upsert_document(doc)

    return IngestResult(
        doc_id=doc_id,
        title=doc["title"],
        pages=len(pages),
        chunks=len(chunks),
        status=doc["status"],
        department=doc["department"],
    )
