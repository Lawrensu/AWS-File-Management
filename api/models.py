"""C1. Pydantic models mirroring contracts/api.md. Keep in sync with web/lib/types.ts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["current", "superseded", "draft"]
Lang = Literal["ms", "en", "mixed"]
Confidence = Literal["high", "medium", "low"]

MAX_TOP_K = 50


class SearchFilters(BaseModel):
    department: str | None = None  # None or "Umum" means no department filter
    doc_type: str | None = None
    include_superseded: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int = Field(default=10, ge=1, le=MAX_TOP_K)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int = Field(default=10, ge=1, le=MAX_TOP_K)  # ignored: /ask picks 8 or 5 chunks
    stream: bool = False


class SearchResult(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    page: int
    snippet: str
    score: float
    doc_type: str | None
    department: str | None
    status: Status
    superseded_by: str | None
    lang: Lang | None


class SearchResponse(BaseModel):
    results: list[SearchResult]


class Citation(BaseModel):
    n: int
    chunk_id: str
    doc_id: str
    title: str
    page: int
    status: Status
    quote: str


class AskResponse(BaseModel):
    answer: str
    language: Lang
    confidence: Confidence
    citations: list[Citation]
    not_found: bool


class UploadResponse(BaseModel):
    doc_id: str
    title: str
    pages: int
    chunks: int
    status: Status
    department: str


class HealthResponse(BaseModel):
    ok: bool
    documents: int
    chunks: int
