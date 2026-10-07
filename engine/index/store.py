"""IndexStore interface. Every store implementation must satisfy this.

This file is a cross-workstream contract. A (ingest) writes through it, C (api) reads
through it. Change it only after telling the team.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

# Documents and chunks are plain dicts matching contracts/document.schema.json and
# contracts/chunk.schema.json. Pydantic models live in api/models.py; the engine stays
# dict-based so it has no dependency on the API package.
Document = dict[str, Any]
Chunk = dict[str, Any]


class IndexStore(ABC):
    @abstractmethod
    def upsert_document(self, doc: Document) -> None: ...

    @abstractmethod
    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        """Chunks must include 'embedding'. Replaces existing chunks for the same doc_id."""

    @abstractmethod
    def get_document(self, doc_id: str) -> Document | None: ...

    @abstractmethod
    def list_documents(self) -> list[Document]: ...

    @abstractmethod
    def get_chunk(self, chunk_id: str) -> Chunk | None: ...

    @abstractmethod
    def chunks_for_document(self, doc_id: str) -> list[Chunk]: ...

    @abstractmethod
    def bm25_search(self, query: str, k: int) -> list[tuple[str, float]]:
        """Returns [(chunk_id, score)] best first."""

    @abstractmethod
    def vector_search(self, query_vec: np.ndarray, k: int) -> list[tuple[str, float]]:
        """Cosine similarity. Returns [(chunk_id, score)] best first."""

    @abstractmethod
    def count(self) -> tuple[int, int]:
        """(documents, chunks)"""


class SqliteStore(IndexStore):
    """B1. In-process store: SQLite for persistence, rank_bm25 + numpy in memory.

    TODO(B): implement. See docs/PLAN.md task B1.
    """

    def __init__(self, path: str) -> None:
        raise NotImplementedError("B1")
