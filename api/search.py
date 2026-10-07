"""C2. POST /search."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import Store, query_vector, to_filters
from api.models import SearchRequest, SearchResponse
from engine.index.hybrid import hybrid_search

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, store: Store) -> SearchResponse:
    results = hybrid_search(
        store, req.query, query_vector(req.query), to_filters(req.filters), req.top_k
    )
    return SearchResponse(results=results)
