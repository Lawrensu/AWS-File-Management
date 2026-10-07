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
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def invoke_model(self, **kw: object) -> dict:
        self.calls.append(kw)
        text = json.loads(kw["body"])["inputText"]  # type: ignore[arg-type]
        seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        vec = np.random.default_rng(seed).standard_normal(DIM).tolist()
        return {"body": io.BytesIO(json.dumps({"embedding": vec}).encode())}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeBedrock:
    monkeypatch.setenv("EMBED_CACHE_PATH", str(tmp_path / "e.sqlite"))
    monkeypatch.delenv("EMBED_FAKE", raising=False)
    client = FakeBedrock()
    monkeypatch.setattr(embed, "_bedrock_client", lambda: client)
    return client


def test_repeat_call_makes_zero_api_calls(fake: FakeBedrock) -> None:
    first = embed_texts(["a", "b"])
    assert len(fake.calls) == 2
    second = embed_texts(["a", "b"])
    assert len(fake.calls) == 2
    np.testing.assert_array_equal(first, second)


def test_request_body(fake: FakeBedrock) -> None:
    embed_texts(["hello"])
    call = fake.calls[0]
    assert call["modelId"] == "amazon.titan-embed-text-v2:0"
    assert json.loads(call["body"]) == {"inputText": "hello", "dimensions": 1024, "normalize": True}


def test_duplicates_in_one_call_embedded_once(fake: FakeBedrock) -> None:
    out = embed_texts(["a", "a", "c"])
    assert len(fake.calls) == 2
    np.testing.assert_array_equal(out[0], out[1])


def test_shape_dtype_and_normalised(fake: FakeBedrock) -> None:
    out = embed_texts(["one", "two", "three"])
    assert out.shape == (3, DIM)
    assert out.dtype == np.float32
    assert np.allclose(np.linalg.norm(out, axis=1), 1, atol=1e-5)


def test_blank_text_is_zero_row_without_call(fake: FakeBedrock) -> None:
    out = embed_texts(["   ", "x"])
    assert len(fake.calls) == 1
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


def test_partial_failure_caches_successes(fake: FakeBedrock) -> None:
    real_invoke = fake.invoke_model

    def flaky(**kw: object) -> dict:
        if json.loads(kw["body"])["inputText"] == "bad":  # type: ignore[arg-type]
            fake.calls.append(kw)
            raise RuntimeError("throttled")
        return real_invoke(**kw)

    fake.invoke_model = flaky  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="throttled"):
        embed_texts(["a", "bad", "b"])
    assert len(fake.calls) == 3

    fake.invoke_model = real_invoke  # type: ignore[method-assign]
    out = embed_texts(["a", "bad", "b"])
    assert len(fake.calls) == 4  # only "bad" is re-requested
    assert out.shape == (3, DIM)
