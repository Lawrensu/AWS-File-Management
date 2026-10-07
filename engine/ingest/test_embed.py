from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest

from engine.ingest import embed
from engine.ingest.embed import DIM, embed_texts


class FakeBedrock:
    """Stub bedrock-runtime client that answers both Cohere and Titan request shapes."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def invoke_model(self, **kw: object) -> dict:
        self.calls.append(kw)
        body = json.loads(kw["body"])  # type: ignore[arg-type]
        if "texts" in body:
            rows = [_vec(t, body["input_type"]) for t in body["texts"]]
            return {"body": io.BytesIO(json.dumps({"embeddings": rows}).encode())}
        return {"body": io.BytesIO(json.dumps({"embedding": _vec(body["inputText"], "")}).encode())}


def _vec(text: str, salt: str) -> list[float]:
    seed = int(hashlib.sha256(f"{salt}|{text}".encode()).hexdigest()[:8], 16)
    return np.random.default_rng(seed).standard_normal(DIM).tolist()


def _bodies(fake: FakeBedrock) -> list[dict]:
    return [json.loads(c["body"]) for c in fake.calls]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeBedrock:
    monkeypatch.setenv("EMBED_CACHE_PATH", str(tmp_path / "e.sqlite"))
    monkeypatch.delenv("EMBED_FAKE", raising=False)
    monkeypatch.delenv("BEDROCK_EMBED_MODEL", raising=False)
    client = FakeBedrock()
    monkeypatch.setattr(embed, "_bedrock_client", lambda: client)
    return client


@pytest.fixture
def titan(fake: FakeBedrock, monkeypatch: pytest.MonkeyPatch) -> FakeBedrock:
    monkeypatch.setenv("BEDROCK_EMBED_MODEL", "amazon.titan-embed-text-v2:0")
    return fake


def test_repeat_call_makes_zero_api_calls(fake: FakeBedrock) -> None:
    first = embed_texts(["a", "b"])
    assert len(fake.calls) == 1
    second = embed_texts(["a", "b"])
    assert len(fake.calls) == 1
    np.testing.assert_array_equal(first, second)


def test_cohere_request_body_document(fake: FakeBedrock) -> None:
    embed_texts(["hello", "world"])
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["modelId"] == "cohere.embed-multilingual-v3"
    assert json.loads(call["body"]) == {
        "texts": ["hello", "world"],
        "input_type": "search_document",
        "truncate": "END",
    }


def test_cohere_request_body_query(fake: FakeBedrock) -> None:
    embed_texts(["hello"], input_type="query")
    assert json.loads(fake.calls[0]["body"]) == {
        "texts": ["hello"],
        "input_type": "search_query",
        "truncate": "END",
    }


def test_invalid_input_type_rejected(fake: FakeBedrock) -> None:
    with pytest.raises(ValueError):
        embed_texts(["x"], input_type="passage")


def test_batches_of_96(fake: FakeBedrock) -> None:
    texts = [f"t{i}" for i in range(200)]
    out = embed_texts(texts)
    assert [len(b["texts"]) for b in _bodies(fake)] == [96, 96, 8]
    assert out.shape == (200, DIM)
    assert np.allclose(np.linalg.norm(out, axis=1), 1, atol=1e-5)
    embed_texts(texts)
    assert len(fake.calls) == 3  # all cached


def test_query_and_document_do_not_share_cache(fake: FakeBedrock) -> None:
    doc = embed_texts(["same text"], input_type="document")
    qry = embed_texts(["same text"], input_type="query")
    assert len(fake.calls) == 2
    assert not np.array_equal(doc, qry)
    np.testing.assert_array_equal(embed_texts(["same text"], input_type="query"), qry)
    np.testing.assert_array_equal(embed_texts(["same text"]), doc)
    assert len(fake.calls) == 2


def test_models_do_not_share_cache(fake: FakeBedrock, monkeypatch: pytest.MonkeyPatch) -> None:
    embed_texts(["x"])
    monkeypatch.setenv("BEDROCK_EMBED_MODEL", "cohere.embed-english-v3")
    embed_texts(["x"])
    assert [c["modelId"] for c in fake.calls] == [
        "cohere.embed-multilingual-v3",
        "cohere.embed-english-v3",
    ]


def test_titan_request_body_one_text_per_call(titan: FakeBedrock) -> None:
    out = embed_texts(["hello", "world"])
    assert len(titan.calls) == 2
    assert titan.calls[0]["modelId"] == "amazon.titan-embed-text-v2:0"
    assert _bodies(titan)[0] == {"inputText": "hello", "dimensions": 1024, "normalize": True}
    assert out.shape == (2, DIM)
    embed_texts(["hello", "world"])
    assert len(titan.calls) == 2


def test_duplicates_in_one_call_embedded_once(fake: FakeBedrock) -> None:
    out = embed_texts(["a", "a", "c"])
    assert _bodies(fake)[0]["texts"] == ["a", "c"]
    np.testing.assert_array_equal(out[0], out[1])


def test_shape_dtype_and_normalised(fake: FakeBedrock) -> None:
    out = embed_texts(["one", "two", "three"])
    assert out.shape == (3, DIM)
    assert out.dtype == np.float32
    assert np.allclose(np.linalg.norm(out, axis=1), 1, atol=1e-5)


def test_blank_text_is_zero_row_without_call(fake: FakeBedrock) -> None:
    out = embed_texts(["   ", "x"])
    assert _bodies(fake)[0]["texts"] == ["x"]
    assert not out[0].any()


def test_empty_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EMBED_CACHE_PATH", str(tmp_path / "e.sqlite"))
    monkeypatch.delenv("EMBED_FAKE", raising=False)
    calls = []
    monkeypatch.setattr(embed, "_bedrock_client", lambda: calls.append(1))
    out = embed_texts([])
    assert out.shape == (0, DIM)
    assert calls == []
    assert not (tmp_path / "e.sqlite").exists()


def test_embed_fake_is_deterministic_and_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EMBED_FAKE", "1")
    monkeypatch.setenv("EMBED_CACHE_PATH", str(tmp_path / "e.sqlite"))

    def boom() -> None:
        raise AssertionError("EMBED_FAKE must not create a Bedrock client")

    monkeypatch.setattr(embed, "_bedrock_client", boom)
    a = embed_texts(["x", "y"])
    b = embed_texts(["x", "y"])
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a[0], a[1])
    assert a.shape == (2, DIM) and a.dtype == np.float32
    assert np.allclose(np.linalg.norm(a, axis=1), 1, atol=1e-5)
    assert not (tmp_path / "e.sqlite").exists()


def test_partial_failure_caches_earlier_batches(fake: FakeBedrock) -> None:
    real_invoke = fake.invoke_model
    texts = [f"t{i}" for i in range(100)]  # two batches: 96 + 4

    def flaky(**kw: object) -> dict:
        if len(json.loads(kw["body"])["texts"]) == 4:  # type: ignore[arg-type]
            fake.calls.append(kw)
            raise RuntimeError("throttled")
        return real_invoke(**kw)

    fake.invoke_model = flaky  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="throttled"):
        embed_texts(texts)
    assert len(fake.calls) == 2

    fake.invoke_model = real_invoke  # type: ignore[method-assign]
    out = embed_texts(texts)
    assert len(fake.calls) == 3  # only the failed batch is re-requested
    assert len(_bodies(fake)[2]["texts"]) == 4
    assert out.shape == (100, DIM)


def test_bedrock_client_uses_adaptive_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    import boto3

    seen: dict = {}

    def fake_client(service: str, **kw: object) -> object:
        seen["service"], seen["kw"] = service, kw
        return object()

    monkeypatch.setattr(boto3, "client", fake_client)
    embed._bedrock_client()
    assert seen["service"] == "bedrock-runtime"
    assert seen["kw"]["config"].retries == {"mode": "adaptive", "max_attempts": 8}
