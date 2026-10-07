"""Shared test doubles so every workstream can build and test before B1's SqliteStore exists.

    from engine.testing import FakeStore, make_document, make_chunk

FakeStore is a complete in-memory IndexStore. bm25_search is plain term overlap, not BM25.
Not used in the demo.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone

import numpy as np

from engine.index.store import Chunk, Document, IndexStore

_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class FakeStore(IndexStore):
    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}
        self._chunks: dict[str, Chunk] = {}

    def upsert_document(self, doc: Document) -> None:
        self._docs[doc["doc_id"]] = copy.deepcopy(doc)

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        doc_ids = {c["doc_id"] for c in chunks}
        for cid in [cid for cid, c in self._chunks.items() if c["doc_id"] in doc_ids]:
            del self._chunks[cid]
        for c in chunks:
            self._chunks[c["chunk_id"]] = copy.deepcopy(c)

    def get_document(self, doc_id: str) -> Document | None:
        d = self._docs.get(doc_id)
        return copy.deepcopy(d) if d else None

    def list_documents(self) -> list[Document]:
        return [copy.deepcopy(d) for d in self._docs.values()]

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        c = self._chunks.get(chunk_id)
        return _without_embedding(c) if c else None

    def chunks_for_document(self, doc_id: str) -> list[Chunk]:
        return [_without_embedding(c) for c in self._chunks.values() if c["doc_id"] == doc_id]

    def bm25_search(self, query: str, k: int) -> list[tuple[str, float]]:
        q = set(tokenize(query))
        if not q:
            return []
        scored = []
        for cid, c in self._chunks.items():
            overlap = len(q & set(tokenize(c["text"])))
            if overlap:
                scored.append((cid, float(overlap)))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]

    def vector_search(self, query_vec: np.ndarray, k: int) -> list[tuple[str, float]]:
        ids = [cid for cid, c in self._chunks.items() if c.get("embedding") is not None]
        if not ids:
            return []
        m = np.array([self._chunks[cid]["embedding"] for cid in ids], dtype=np.float32)
        m = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)
        q = np.asarray(query_vec, dtype=np.float32)
        q = q / (np.linalg.norm(q) + 1e-9)
        sims = m @ q
        order = np.argsort(-sims)[:k]
        return [(ids[i], float(sims[i])) for i in order]

    def count(self) -> tuple[int, int]:
        return len(self._docs), len(self._chunks)


def _without_embedding(c: Chunk) -> Chunk:
    c = copy.deepcopy(c)
    c.pop("embedding", None)
    return c


def make_document(doc_id: str = "a1b2c3d4e5f60718", **overrides) -> Document:
    doc: Document = {
        "doc_id": doc_id,
        "title": "Pekeliling Kewangan Bil. 3/2024 Kadar Elaun Perjalanan",
        "filename": "02-pekeliling-elaun-perjalanan-2024.pdf",
        "source_path": "samples/02-pekeliling-elaun-perjalanan-2024.pdf",
        "doc_type": "circular",
        "department": "Jabatan Kewangan",
        "topics": ["elaun_dan_tuntutan"],
        "year": 2024,
        "lang": "ms",
        "status": "current",
        "supersedes": [],
        "superseded_by": None,
        "keywords": ["elaun perjalanan", "kadar"],
        "page_count": 3,
        "has_scanned_pages": False,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(overrides)
    return doc


def make_chunk(doc_id: str = "a1b2c3d4e5f60718", page: int = 1, n: int = 0,
               text: str = "Kadar elaun perjalanan bagi kontraktor adalah RM0.70 sekilometer.",
               dim: int = 1024, seed: int | None = None, **overrides) -> Chunk:
    if seed is None:
        seed = abs(hash((doc_id, page, n))) % 2**32
    rng = np.random.default_rng(seed)
    chunk: Chunk = {
        "chunk_id": f"{doc_id}:{page}:{n}",
        "doc_id": doc_id,
        "page": page,
        "bbox": [72.0, 100.0, 540.0, 160.0],
        "heading": None,
        "text": text,
        "lang": "ms",
        "source": "native",
        "embedding": rng.standard_normal(dim).astype(np.float32).tolist(),
    }
    chunk.update(overrides)
    return chunk
