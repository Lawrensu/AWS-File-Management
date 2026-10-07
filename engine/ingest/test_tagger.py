from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from engine.ingest import tagger
from engine.ingest.tagger import RETRY_PREFIX, tag_document

FILENAME = "02-pekeliling-elaun-perjalanan-2024.pdf"
TEXT = "PEKELILING KEWANGAN BIL. 3/2024\nPekeliling ini menggantikan Pekeliling Bil. 2/2022."

VALID = {
    "title": "Pekeliling Kewangan Bil. 3/2024",
    "doc_type": "circular",
    "department": "Jabatan Kewangan",
    "topics": ["elaun_dan_tuntutan"],
    "year": 2024,
    "lang": "ms",
    "supersedes": ["Pekeliling Bil. 2/2022"],
    "summary": "Pekeliling ini menetapkan kadar elaun perjalanan baharu.",
}


class FakeMessages:
    def __init__(self, replies: list[str | Exception]) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    def create(self, **kw: object) -> SimpleNamespace:
        self.calls.append(kw)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=reply)])


def _install(monkeypatch: pytest.MonkeyPatch, replies: list[str | Exception]) -> FakeMessages:
    messages = FakeMessages(replies)
    monkeypatch.setattr(tagger, "_client", lambda: SimpleNamespace(messages=messages))
    return messages


def _user(call: dict) -> str:
    return call["messages"][0]["content"]


def test_valid_json_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, [json.dumps(VALID)])
    assert tag_document(FILENAME, TEXT) == VALID
    assert len(fake.calls) == 1


def test_prompt_comes_from_tagger_md(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, [json.dumps(VALID)])
    long_text = "x" * 9000
    tag_document(FILENAME, long_text)
    call = fake.calls[0]
    assert call["system"].startswith("You classify Malaysian government agency documents.")
    assert call["system"] == tagger._prompts()[0]
    user = _user(call)
    assert FILENAME in user
    assert "Jabatan Kewangan" in user
    assert "{{" not in user
    assert "x" * 6000 in user and "x" * 6001 not in user


def test_invalid_then_valid_retries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, ["not json", json.dumps(VALID)])
    assert tag_document(FILENAME, TEXT) == VALID
    assert len(fake.calls) == 2
    assert _user(fake.calls[1]).startswith(RETRY_PREFIX)
    assert _user(fake.calls[1]).endswith(_user(fake.calls[0]))


def test_invalid_twice_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, ["nope", "[1, 2]"])
    assert tag_document(FILENAME, TEXT) == tagger.fallback(FILENAME)
    assert len(fake.calls) == 2


def test_fallback_values() -> None:
    fb = tagger.fallback(FILENAME)
    assert fb["doc_type"] == "other"
    assert fb["department"] == "Umum"
    assert fb["topics"] == ["lain"]
    assert fb["supersedes"] == []
    assert fb["title"] == FILENAME


def test_client_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_creds() -> None:
        raise RuntimeError("no credentials")

    monkeypatch.setattr(tagger, "_client", no_creds)
    assert tag_document(FILENAME, TEXT) == tagger.fallback(FILENAME)


def test_api_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, [ConnectionError("boom")])
    assert tag_document(FILENAME, TEXT) == tagger.fallback(FILENAME)
    assert len(fake.calls) == 1


def test_out_of_taxonomy_values_coerced(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = {
        **VALID,
        "doc_type": "memo",
        "department": "Finance",
        "topics": ["x", "cuti"],
        "year": "2024",
        "lang": "fr",
        "supersedes": ["", 3, "Bil. 1/2020"],
        "title": "",
    }
    _install(monkeypatch, [json.dumps(bad)])
    out = tag_document(FILENAME, TEXT)
    assert out["doc_type"] == "other"
    assert out["department"] == "Umum"
    assert out["topics"] == ["cuti"]
    assert out["year"] == 2024
    assert out["lang"] is None
    assert out["supersedes"] == ["Bil. 1/2020"]
    assert out["title"] == FILENAME


def test_no_valid_topics_becomes_lain(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, [json.dumps({**VALID, "topics": ["x"], "year": True})])
    out = tag_document(FILENAME, TEXT)
    assert out["topics"] == ["lain"]
    assert out["year"] is None


def test_fenced_json_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, ["```json\n" + json.dumps(VALID) + "\n```"])
    assert tag_document(FILENAME, TEXT) == VALID


def test_empty_text_makes_no_call(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, [])
    assert tag_document(FILENAME, "   \n ") == tagger.fallback(FILENAME)
    assert fake.calls == []


def test_embed_fake_returns_fallback_without_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_FAKE", "1")
    created: list[int] = []

    def must_not_be_called() -> None:
        created.append(1)  # tag_document swallows exceptions, so record the call instead
        raise AssertionError("client must not be created in fake mode")

    monkeypatch.setattr(tagger, "_client", must_not_be_called)
    assert tag_document(FILENAME, TEXT) == tagger.fallback(FILENAME)
    assert created == []
