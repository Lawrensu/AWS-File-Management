"""A3. Embeddings on Bedrock via boto3, cached in SQLite by sha256 of model, input type and text.

Default model is Cohere Embed Multilingual v3 (cohere.embed-multilingual-v3, 1024 dims, on
demand in ap-southeast-1). A model ID starting with "amazon.titan" switches to the Titan v2
request shape, so going back is a config change. Cohere truncates input past 512 tokens.

EMBED_FAKE=1 returns deterministic hash-seeded vectors and never touches AWS or the cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np

DIM = 1024
DEFAULT_MODEL = "cohere.embed-multilingual-v3"
BATCH_SIZE = 96  # Cohere accepts up to 96 texts per request
_COHERE_INPUT_TYPES = {"document": "search_document", "query": "search_query"}


def embed_texts(texts: list[str], input_type: str = "document") -> np.ndarray:
    """Return (len(texts), 1024) float32, rows L2-normalised.

    input_type is "document" (default, for ingest) or "query". API code embedding a user
    question must pass input_type="query"; Cohere embeds the two differently.

    Exception: whitespace-only texts get a zero row and no API call. Only cache misses are
    sent to Bedrock: Cohere in batches of 96, Titan one invoke_model per text.
    """
    if input_type not in _COHERE_INPUT_TYPES:
        raise ValueError(f"input_type must be 'document' or 'query', got {input_type!r}")
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    if os.environ.get("EMBED_FAKE") == "1":
        return np.vstack([_fake_vector(t) for t in texts])

    model = os.environ.get("BEDROCK_EMBED_MODEL", DEFAULT_MODEL)
    keys = [_key(model, input_type, t) for t in texts]
    out = np.zeros((len(texts), DIM), dtype=np.float32)

    with closing(_open_cache()) as con:
        found = _lookup(con, model, set(keys))
        misses: dict[str, str] = {}
        for t, k in zip(texts, keys):
            if k not in found and k not in misses and t.strip():
                misses[k] = t
        if misses:
            client = _bedrock_client()
            new: dict[str, np.ndarray] = {}
            try:
                _embed_misses(client, model, input_type, misses, new)
            finally:
                # Cache every success, even when a later batch raised, so a retry only pays
                # for what failed.
                with con:
                    con.executemany(
                        "INSERT OR REPLACE INTO embeddings (key, model, vec) VALUES (?, ?, ?)",
                        [(k, model, v.tobytes()) for k, v in new.items()],
                    )
            found.update(new)

    for i, k in enumerate(keys):
        if k in found:
            out[i] = found[k]
    return out


def _embed_misses(
    client: Any, model: str, input_type: str, misses: dict[str, str], new: dict[str, np.ndarray]
) -> None:
    items = list(misses.items())
    if model.startswith("amazon.titan"):
        for k, t in items:  # Titan v2 takes a single input per request
            new[k] = _invoke_titan(client, model, t)
        return
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        vecs = _invoke_cohere(client, model, input_type, [t for _, t in batch])
        for (k, _), v in zip(batch, vecs):
            new[k] = v


def _bedrock_client() -> Any:
    import boto3
    from botocore.config import Config

    region = os.environ.get("AWS_REGION", "ap-southeast-1")
    config = Config(retries={"mode": "adaptive", "max_attempts": 8})
    return boto3.client("bedrock-runtime", region_name=region, config=config)


def _invoke_cohere(client: Any, model: str, input_type: str, texts: list[str]) -> list[np.ndarray]:
    resp = client.invoke_model(
        modelId=model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {"texts": texts, "input_type": _COHERE_INPUT_TYPES[input_type], "truncate": "END"}
        ),
    )
    rows = json.loads(resp["body"].read())["embeddings"]
    if len(rows) != len(texts):
        raise ValueError(f"expected {len(texts)} embeddings, got {len(rows)}")
    return [_normalise(np.asarray(r, dtype=np.float32)) for r in rows]


def _invoke_titan(client: Any, model: str, text: str) -> np.ndarray:
    resp = client.invoke_model(
        modelId=model,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text, "dimensions": DIM, "normalize": True}),
    )
    vec = np.asarray(json.loads(resp["body"].read())["embedding"], dtype=np.float32)
    return _normalise(vec)


def _cache_path() -> Path:
    default = Path.home() / ".cache" / "rujuk" / "embed.sqlite"
    return Path(os.environ.get("EMBED_CACHE_PATH") or default)


def _open_cache() -> sqlite3.Connection:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS embeddings "
        "(key TEXT, model TEXT, vec BLOB, PRIMARY KEY (key, model))"
    )
    return con


def _lookup(con: sqlite3.Connection, model: str, keys: set[str]) -> dict[str, np.ndarray]:
    found: dict[str, np.ndarray] = {}
    key_list = list(keys)
    for i in range(0, len(key_list), 500):  # stay under SQLite's bound-parameter limit
        batch = key_list[i : i + 500]
        marks = ",".join("?" * len(batch))
        rows = con.execute(
            f"SELECT key, vec FROM embeddings WHERE model = ? AND key IN ({marks})",
            [model, *batch],
        )
        for k, blob in rows:
            found[k] = np.frombuffer(blob, dtype=np.float32).copy()
    return found


def _key(model: str, input_type: str, text: str) -> str:
    return hashlib.sha256(f"{model}\x1f{input_type}\x1f{text}".encode()).hexdigest()


def _fake_vector(text: str) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    return _normalise(np.random.default_rng(seed).standard_normal(DIM).astype(np.float32))


def _normalise(vec: np.ndarray) -> np.ndarray:
    vec = vec.astype(np.float32)
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec
