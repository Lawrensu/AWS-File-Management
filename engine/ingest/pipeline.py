"""A6. One file into the index: extract, chunk, detect language, tag, embed, upsert."""

from __future__ import annotations

import hashlib
import sys
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
    scanned_pages_skipped: int = 0  # scanned pages left out of the index (no OCR yet)
    embedding_failed: bool = False  # True when embedding failed and chunks have no vectors


def ingest_file(path: str | Path, store: IndexStore, force: bool = False) -> IngestResult:
    """Ingest one PDF. Idempotent on doc_id = sha256(file bytes)[:16].

    An existing doc_id is skipped unless force is True, which re-ingests it and replaces
    its chunks.
    """
    path = Path(path)
    doc_id = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

    existing = store.get_document(doc_id)
    if existing is not None and not force:
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
    scanned_skipped = len(pages) - len(text_pages)
    chunks = chunk_pages(doc_id, text_pages)
    for chunk in chunks:
        chunk["lang"] = detect_lang(chunk["text"])  # local langdetect, not a model call

    head = "\n".join(p.text for p in pages[:TAG_PAGES])
    tags = tag_document(path.name, head)  # once per document

    full_text = "\n".join(p.text for p in text_pages)
    lang = tags["lang"] or detect_lang(full_text)
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
        "summary": tags.get("summary") or None,
        "keywords": extract_keywords(full_text, lang),
        "page_count": len(pages),
        "has_scanned_pages": any(p.is_scanned for p in pages),
        "ingested_at": datetime.now(UTC).isoformat(),
    }

    embedding_failed = False
    if chunks:
        try:
            vecs = embed_texts([c["text"] for c in chunks])  # one batch per document
            for chunk, vec in zip(chunks, vecs):
                chunk["embedding"] = vec
        except Exception as exc:  # noqa: BLE001 - a Bedrock failure must never crash ingest
            print(f"warning: no embeddings for {path.name} ({type(exc).__name__})", file=sys.stderr)
            embedding_failed = True
            for chunk in chunks:
                chunk["embedding"] = None  # search falls back to BM25 for these chunks

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
        scanned_pages_skipped=scanned_skipped,
        embedding_failed=embedding_failed,
    )
