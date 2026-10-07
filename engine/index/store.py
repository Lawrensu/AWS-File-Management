"""IndexStore interface. Every store implementation must satisfy this.

This file is a cross-workstream contract. A (ingest) writes through it, C (api) reads
through it. Change it only after telling the team.
"""

from __future__ import annotations

import copy
import json
import math
import numbers
import re
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

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


_TOKEN = re.compile(r"\w+", re.UNICODE)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    data   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id  TEXT PRIMARY KEY,
    doc_id    TEXT NOT NULL,
    data      TEXT NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS chunks_by_doc ON chunks (doc_id);
"""


# Function words in both languages. Without them an English question gets keyword hits on
# "what is the" in English chunks, and with vectors on those hits outrank a Malay answer
# that only the vectors can find. English "had" is left out: in Malay it means "limit".
_STOPWORDS = frozenset(
    """
    a an the is are was were be been being do does did of to in on at by for from with and
    or not this that these those it its what which who whom how many much when where why
    must should can will shall would could
    dan yang di ke dari daripada untuk bagi dengan ini itu adalah ialah oleh pada dalam akan
    telah boleh mesti hendaklah berapa berapakah apakah siapakah bilakah manakah atau juga
    tidak ada sebagai kepada semua setiap
    """.split()  # noqa: SIM905 - a word list reads better than 80 quoted strings
)


def tokenize(text: str) -> list[str]:
    """Lowercased unicode word tokens minus stopwords, used for indexing and queries."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class _LuceneBM25(BM25Okapi):
    """BM25Okapi with Lucene's idf, which is always positive.

    rank_bm25's own idf is zero or negative for a term in half the chunks or more, so a
    one-PDF index (the 1:30 vertical slice) gets no keyword hits at all.
    """

    def _calc_idf(self, nd: dict[str, int]) -> None:
        for word, freq in nd.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))


class SqliteStore(IndexStore):
    """B1. SQLite for persistence; documents, chunks, BM25 and vectors held in memory.

    Safe to share across threads: one connection, every access under an RLock, so FastAPI
    can open it in the lifespan and use it from its thread pool. Every read checks
    PRAGMA data_version and reloads when another connection (the ingest CLI) has committed.
    Writes mark the search index stale and the next search rebuilds it, so a bulk ingest
    rebuilds once. Reads return copies, and chunks never carry their embedding.
    """

    def __init__(self, path: str | Path) -> None:
        path = str(path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._con = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        self._con.executescript(_SCHEMA)
        self._data_version = -1
        self._docs: dict[str, Document] = {}
        self._chunks: dict[str, Chunk] = {}  # without "embedding"
        self._vectors: dict[str, np.ndarray] = {}  # chunk_id -> float32 row, as stored
        self._stale = True
        self._bm25: _LuceneBM25 | None = None
        self._bm25_ids: list[str] = []
        self._matrix: np.ndarray | None = None  # rows L2-normalised
        self._matrix_ids: list[str] = []
        with self._lock:
            self._refresh()

    def close(self) -> None:
        with self._lock:
            self._con.close()

    # Writes

    def upsert_document(self, doc: Document) -> None:
        doc_id = _require(doc, "doc_id")
        data = _dumps(doc)
        with self._lock, self._con:
            self._con.execute(
                "INSERT INTO documents (doc_id, data) VALUES (?, ?) "
                "ON CONFLICT (doc_id) DO UPDATE SET data = excluded.data",
                (doc_id, data),
            )
            self._docs[doc_id] = json.loads(data)

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        rows, parsed, vectors = [], {}, {}
        for c in chunks:
            chunk_id = _require(c, "chunk_id")
            page = c.get("page")
            if not isinstance(page, numbers.Integral) or isinstance(page, bool) or page < 1:
                raise ValueError(f"chunk {chunk_id}: page must be an integer >= 1, got {page!r}")
            if chunk_id in parsed:
                raise ValueError(f"duplicate chunk_id {chunk_id} in one upsert")
            data = _dumps({k: v for k, v in c.items() if k != "embedding"})
            emb = c.get("embedding")
            vec = None if emb is None else np.asarray(emb, dtype=np.float32).ravel()
            rows.append(
                (chunk_id, _require(c, "doc_id"), data, None if vec is None else vec.tobytes())
            )
            parsed[chunk_id] = json.loads(data)
            if vec is not None:
                vectors[chunk_id] = vec
        doc_ids = {c["doc_id"] for c in parsed.values()}

        with self._lock:
            self._refresh()
            kept = (
                v for cid, v in self._vectors.items() if self._chunks[cid]["doc_id"] not in doc_ids
            )
            dims = {v.shape[0] for v in vectors.values()} | {v.shape[0] for v in kept}
            if len(dims) > 1:
                raise ValueError(f"embedding dimensions differ in the index: {sorted(dims)}")
            with self._con:
                self._con.executemany(
                    "DELETE FROM chunks WHERE doc_id = ?", [(d,) for d in doc_ids]
                )
                self._con.executemany(
                    "INSERT INTO chunks (chunk_id, doc_id, data, embedding) VALUES (?, ?, ?, ?)",
                    rows,
                )
            for cid in [cid for cid, c in self._chunks.items() if c["doc_id"] in doc_ids]:
                del self._chunks[cid]
                self._vectors.pop(cid, None)
            self._chunks.update(parsed)
            self._vectors.update(vectors)
            self._stale = True

    # Reads

    def get_document(self, doc_id: str) -> Document | None:
        with self._lock:
            self._refresh()
            doc = self._docs.get(doc_id)
            return copy.deepcopy(doc) if doc is not None else None

    def list_documents(self) -> list[Document]:
        with self._lock:
            self._refresh()
            return copy.deepcopy(list(self._docs.values()))

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        with self._lock:
            self._refresh()
            chunk = self._chunks.get(chunk_id)
            return copy.deepcopy(chunk) if chunk is not None else None

    def chunks_for_document(self, doc_id: str) -> list[Chunk]:
        with self._lock:
            self._refresh()
            chunks = [c for c in self._chunks.values() if c["doc_id"] == doc_id]
            return copy.deepcopy(sorted(chunks, key=_page_order))

    def count(self) -> tuple[int, int]:
        with self._lock:
            self._refresh()
            return len(self._docs), len(self._chunks)

    def bm25_search(self, query: str, k: int) -> list[tuple[str, float]]:
        tokens = tokenize(query)
        with self._lock:
            self._refresh()
            self._ensure_index()
            bm25, ids = self._bm25, self._bm25_ids
            if bm25 is None or not tokens or k <= 0:
                return []
            scores = bm25.get_scores(tokens)
        order = np.argsort(-scores, kind="stable")[:k]
        return [(ids[i], float(scores[i])) for i in order if scores[i] > 0]

    def vector_search(self, query_vec: np.ndarray, k: int) -> list[tuple[str, float]]:
        q = np.asarray(query_vec, dtype=np.float32).ravel()
        with self._lock:
            self._refresh()
            self._ensure_index()
            matrix, ids = self._matrix, self._matrix_ids
        if matrix is None or k <= 0:
            return []
        if q.shape[0] != matrix.shape[1]:
            raise ValueError(f"query dimension {q.shape[0]} != index dimension {matrix.shape[1]}")
        norm = np.linalg.norm(q)
        if norm == 0:
            return []
        sims = matrix @ (q / norm)
        order = np.argsort(-sims, kind="stable")[:k]
        return [(ids[i], float(sims[i])) for i in order]

    # Internals. Callers hold self._lock.

    def _refresh(self) -> None:
        """Reload everything if another connection committed since the last check."""
        version = self._con.execute("PRAGMA data_version").fetchone()[0]
        if version == self._data_version:
            return
        docs = {
            doc_id: json.loads(data)
            for doc_id, data in self._con.execute(
                "SELECT doc_id, data FROM documents ORDER BY rowid"
            )
        }
        chunks, vectors = {}, {}
        for cid, data, blob in self._con.execute(
            "SELECT chunk_id, data, embedding FROM chunks ORDER BY rowid"
        ):
            chunks[cid] = json.loads(data)
            if blob is not None:
                vectors[cid] = np.frombuffer(blob, dtype=np.float32)
        self._docs, self._chunks, self._vectors = docs, chunks, vectors
        self._data_version = version
        self._stale = True

    def _ensure_index(self) -> None:
        if not self._stale:
            return
        ids = list(self._chunks)
        corpus = [tokenize(self._chunks[cid].get("text") or "") for cid in ids]
        if any(corpus):
            self._bm25, self._bm25_ids = _LuceneBM25(corpus), ids
        else:
            self._bm25, self._bm25_ids = None, []

        vec_ids = [cid for cid in ids if cid in self._vectors]
        self._matrix, self._matrix_ids = None, []
        if vec_ids:
            m = np.vstack([self._vectors[cid] for cid in vec_ids])
            norms = np.linalg.norm(m, axis=1)
            keep = norms > 0
            if keep.any():
                self._matrix = m[keep] / norms[keep, None]
                self._matrix_ids = [cid for cid, ok in zip(vec_ids, keep) if ok]
        self._stale = False


def _require(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    if not value:
        raise ValueError(f"missing {key!r}")
    return value


def _page_order(chunk: Chunk) -> tuple[int, int]:
    n = chunk["chunk_id"].rsplit(":", 1)[-1]
    return chunk["page"], int(n) if n.isdigit() else 0


def _dumps(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


def _json_default(o: Any) -> Any:
    # Ingest hands over numpy scalars and arrays, Paths, and datetimes; store them as JSON.
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"{type(o).__name__} is not JSON serialisable")
