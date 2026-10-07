"""Shared helpers for the C routers: the store, filters, and query embedding."""

from __future__ import annotations

import logging
import os
from typing import Annotated

import numpy as np
from fastapi import Depends, HTTPException, Request

from api.models import SearchFilters
from engine.index.hybrid import Filters
from engine.index.store import IndexStore
from engine.ingest.embed import embed_texts

log = logging.getLogger("api")


def get_store(request: Request) -> IndexStore:
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="index not ready")
    return store


Store = Annotated[IndexStore, Depends(get_store)]


def to_filters(f: SearchFilters) -> Filters:
    return Filters(
        department=f.department, doc_type=f.doc_type, include_superseded=f.include_superseded
    )


def query_vector(text: str) -> np.ndarray | None:
    """Embed a question for vector search. None means BM25 only.

    EMBED_FAKE vectors are random, so they would only add noise to the ranking. Any
    embedding failure also drops to BM25; it never fails the request.
    """
    if os.environ.get("EMBED_FAKE") == "1":
        return None
    try:
        return embed_texts([text], input_type="query")[0]
    except Exception as exc:  # noqa: BLE001 - a Bedrock failure must never crash the API
        log.warning("query embedding failed, BM25 only: %s", type(exc).__name__)
        return None
