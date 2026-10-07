from __future__ import annotations

import json

import pytest

from engine.ingest import tagger
from engine.ingest.tagger import RETRY_PREFIX, tag_document
from engine.llm import LLMResult, LLMUnavailable

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


class FakeComplete:
    """Stands in for engine.llm.complete: records each call, replays the scripted replies."""

    def __init__(self, replies: list[str | Exception]) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    def __call__(self, system: str, user: str, **kw: object) -> LLMResult:
        self.calls.append({"system": system, "user": user, **kw})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(reply, "groq", "stub-model")


def _install(monkeypatch: pytest.MonkeyPatch, replies: list[str | Exception]) -> FakeComplete:
    fake = FakeComplete(replies)
    monkeypatch.setattr(tagger, "complete", fake)
    return fake


def _user(call: dict) -> str:
    return call["user"]


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


def test_no_llm_available_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, [LLMUnavailable("Bedrock down, no Groq key")])
    assert tag_document(FILENAME, TEXT) == tagger.fallback(FILENAME)
    assert len(fake.calls) == 1


def test_json_validate_failed_retried_once(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = LLMUnavailable("groq m failed with BadRequestError: 400 json_validate_failed")
    fake = _install(monkeypatch, [bad, json.dumps(VALID)])
    assert tag_document(FILENAME, TEXT) == VALID
    assert len(fake.calls) == 2


def test_json_validate_failed_twice_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = LLMUnavailable("groq m failed with BadRequestError: 400 json_validate_failed")
    fake = _install(monkeypatch, [bad, bad])
    assert tag_document(FILENAME, TEXT) == tagger.fallback(FILENAME)
    assert len(fake.calls) == 2


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


def test_call_asks_for_the_tag_role_with_the_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, [json.dumps(VALID)])
    tag_document(FILENAME, TEXT)
    call = fake.calls[0]
    assert call["role"] == "tag"
    assert call["max_tokens"] == 1024
    assert list(call["json_schema"]["properties"]) == list(VALID)
    assert call["json_schema"]["required"] == list(VALID)


def test_embed_fake_still_tags_through_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    # llm.complete decides what EMBED_FAKE means (skip Bedrock, use Groq if keyed).
    monkeypatch.setenv("EMBED_FAKE", "1")
    fake = _install(monkeypatch, [json.dumps(VALID)])
    assert tag_document(FILENAME, TEXT) == VALID
    assert len(fake.calls) == 1


def test_embed_fake_without_any_provider_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real engine.llm.complete: fake mode skips Bedrock, an empty key skips Groq.
    monkeypatch.setenv("EMBED_FAKE", "1")
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert tag_document(FILENAME, TEXT) == tagger.fallback(FILENAME)
