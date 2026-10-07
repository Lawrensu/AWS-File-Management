"""C5. POST /documents/upload. Ingests synchronously into the live store."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from api.deps import Store
from api.models import UploadResponse
from engine.index.store import IndexStore
from engine.index.supersession import resolve_supersession
from engine.ingest.pipeline import ingest_file

log = logging.getLogger("api.upload")
router = APIRouter()

MAX_BYTES = 50 * 1024 * 1024
_UNSAFE = re.compile(r"[^\w.\-]+", re.UNICODE)


def upload_dir() -> Path:
    return Path(os.environ.get("UPLOAD_DIR", "data/uploads"))


@router.post("/documents/upload", response_model=UploadResponse)
async def upload(
    store: Store, file: Annotated[UploadFile | None, File()] = None
) -> UploadResponse:
    if file is None:
        raise HTTPException(status_code=400, detail="multipart field 'file' is required")
    name = Path(file.filename or "").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf files are accepted")
    data = await file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="file is empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="file is larger than 50 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="file is not a PDF")

    # Prefix with the content hash so two different files with one name never collide.
    digest = hashlib.sha256(data).hexdigest()[:16]
    path = upload_dir() / f"{digest}-{_UNSAFE.sub('_', name)}"
    return await run_in_threadpool(_ingest, path, data, store)


def _ingest(path: Path, data: bytes, store: IndexStore) -> UploadResponse:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    try:
        result = ingest_file(path, store)
        resolve_supersession(store)
    except Exception as exc:  # report, never take the API down
        log.exception("ingest failed for %s", path.name)
        raise HTTPException(status_code=500, detail=f"ingest failed: {type(exc).__name__}") from exc
    # Supersession may have changed the status of the new document.
    doc = store.get_document(result.doc_id) or {}
    return UploadResponse(
        doc_id=result.doc_id,
        title=result.title,
        pages=result.pages,
        chunks=result.chunks,
        status=doc.get("status", result.status),
        department=result.department,
    )
