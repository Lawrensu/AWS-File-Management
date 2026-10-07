"""A3. Titan Text Embeddings v2 via boto3, cached in SQLite by sha256 of the text.

EMBED_FAKE=1 returns deterministic hash-seeded vectors and never touches AWS or the cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np

DIM = 1024
DEFAULT_MODEL = "amazon.titan-embed-text-v2:0"
MAX_WORKERS = 8


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return (len(texts), 1024) float32, rows L2-normalised.

    Exception: whitespace-only texts get a zero row and no API call (Titan rejects empty
    input). Only cache misses are sent to Bedrock, one invoke_model each (Titan v2 takes a
    single input per request), in a small thread pool.
    """
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    if os.environ.get("EMBED_FAKE") == "1":
        return np.vstack([_fake_vector(t) for t in texts])

    model = os.environ.get("BEDROCK_EMBED_MODEL", DEFAULT_MODEL)
    keys = [_key(t) for t in texts]
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
            first_error: Exception | None = None
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures = {k: pool.submit(_invoke, client, model, t) for k, t in misses.items()}
                for k, fut in futures.items():
                    try:
                        new[k] = fut.result()
                    except Exception as exc:  # noqa: BLE001 - re-raised below after caching
                        first_error = first_error or exc
            # Cache every success before re-raising, so a retry only pays for the failures.
            with con:
                con.executemany(
                    "INSERT OR REPLACE INTO embeddings (key, model, vec) VALUES (?, ?, ?)",
                    [(k, model, v.tobytes()) for k, v in new.items()],
                )
            if first_error is not None:
                raise first_error
            found.update(new)

    for i, k in enumerate(keys):
        if k in found:
            out[i] = found[k]
    return out


def _bedrock_client() -> Any:
    import boto3

    region = os.environ.get("AWS_REGION", "ap-southeast-1")
    return boto3.client("bedrock-runtime", region_name=region)


def _invoke(client: Any, model: str, text: str) -> np.ndarray:
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


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fake_vector(text: str) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    return _normalise(np.random.default_rng(seed).standard_normal(DIM).astype(np.float32))


def _normalise(vec: np.ndarray) -> np.ndarray:
    vec = vec.astype(np.float32)
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec
