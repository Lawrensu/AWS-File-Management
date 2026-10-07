from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine import llm
from engine.llm import LLMUnavailable, complete, preferred_provider, stream

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}, "year": {}}}


class Boom(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clean environment: Groq key set, no fake mode, a fresh breaker, set model IDs."""
    for name in ("EMBED_FAKE", "BEDROCK_CLIENT", "LLM_BEDROCK_COOLDOWN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("AWS_REGION", "test-region-1")
    monkeypatch.setenv("BEDROCK_TAG_MODEL", "bedrock-tag-model")
    monkeypatch.setenv("BEDROCK_ANSWER_MODEL", "bedrock-answer-model")
    monkeypatch.setenv("GROQ_TAG_MODEL", "groq-tag-model")
    monkeypatch.setenv("GROQ_ANSWER_MODEL", "groq-answer-model")
    monkeypatch.setattr(llm, "_bedrock_down_until", {})
    clock = [1000.0]
    monkeypatch.setattr(llm, "_now", lambda: clock[0])
    monkeypatch.setattr(llm, "_test_clock", clock, raising=False)


def advance(seconds: float) -> None:
    llm._test_clock[0] += seconds  # type: ignore[attr-defined]


# --- stub clients, shaped like the real SDKs ---------------------------------------------


class StubMantle:
    """anthropic AnthropicBedrockMantle: messages.create and messages.stream."""

    def __init__(self, text: str = "hello", fail: Exception | None = None, deltas=None) -> None:
        self.text, self.fail, self.deltas = text, fail, deltas
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kw: object) -> SimpleNamespace:
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.text)],
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        )

    def stream(self, **kw: object):
        self.calls.append(kw)
        outer = self

        class Manager:
            def __enter__(self) -> SimpleNamespace:
                if outer.fail:
                    raise outer.fail
                return SimpleNamespace(text_stream=iter_deltas(outer.deltas or ["a", "b"]))

            def __exit__(self, *exc: object) -> None:
                return None

        return Manager()


def iter_deltas(items: list):
    for item in items:
        if isinstance(item, Exception):
            raise item
        yield item


class StubConverse:
    """boto3 bedrock-runtime: converse and converse_stream."""

    def __init__(self, text: str = "hi", fail: Exception | None = None) -> None:
        self.text, self.fail = text, fail
        self.calls: list[dict] = []

    def converse(self, **kw: object) -> dict:
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": self.text}]}},
            "usage": {"inputTokens": 5, "outputTokens": 3},
        }

    def converse_stream(self, **kw: object) -> dict:
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        events = [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockDelta": {"delta": {"text": "x"}, "contentBlockIndex": 0}},
            {"contentBlockDelta": {"delta": {"text": "y"}, "contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "end_turn"}},
        ]
        return {"stream": iter(events)}


class StubGroq:
    """groq.Groq: chat.completions.create, plain or stream=True."""

    def __init__(self, text: str = "kuala lumpur", fail: Exception | None = None) -> None:
        self.text, self.fail = text, fail
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw: object):
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        if kw.get("stream"):
            pieces = ["g1", "g2"]
            empty = SimpleNamespace(choices=[])
            return iter([empty] + [_chunk(p) for p in pieces] + [_chunk(None)])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=4),
        )


def _chunk(text: str | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mantle: StubMantle | None = None,
    converse: StubConverse | None = None,
    groq: StubGroq | None = None,
) -> None:
    def must_not_be_built(*_a: object) -> None:
        raise AssertionError("client of this kind must not be built")

    monkeypatch.setattr(
        llm, "_mantle_client", (lambda region: mantle) if mantle else must_not_be_built
    )
    monkeypatch.setattr(
        llm, "_converse_client", (lambda region: converse) if converse else must_not_be_built
    )
    monkeypatch.setattr(llm, "_groq_client", (lambda key: groq) if groq else must_not_be_built)


# --- complete -----------------------------------------------------------------------------


def test_bedrock_success_via_mantle(monkeypatch: pytest.MonkeyPatch) -> None:
    mantle, groq = StubMantle("bonjour"), StubGroq()
    install(monkeypatch, mantle=mantle, groq=groq)
    out = complete("sys", "usr", role="answer", max_tokens=50)
    assert out == llm.LLMResult("bonjour", "bedrock", "bedrock-answer-model", 11, 7)
    assert mantle.calls == [
        {
            "model": "bedrock-answer-model",
            "max_tokens": 50,
            "system": "sys",
            "messages": [{"role": "user", "content": "usr"}],
        }
    ]
    assert groq.calls == []


def test_role_picks_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    mantle = StubMantle()
    install(monkeypatch, mantle=mantle)
    assert complete("s", "u", role="tag", max_tokens=5).model == "bedrock-tag-model"


def test_unknown_role_rejected() -> None:
    with pytest.raises(ValueError):
        complete("s", "u", role="chat", max_tokens=5)
    with pytest.raises(ValueError):
        preferred_provider("chat")


def test_bedrock_success_via_converse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_CLIENT", "converse")
    converse = StubConverse("salam")
    install(monkeypatch, converse=converse)
    out = complete("sys", "usr", role="tag", max_tokens=9)
    assert out == llm.LLMResult("salam", "bedrock", "bedrock-tag-model", 5, 3)
    assert converse.calls == [
        {
            "modelId": "bedrock-tag-model",
            "system": [{"text": "sys"}],
            "messages": [{"role": "user", "content": [{"text": "usr"}]}],
            "inferenceConfig": {"maxTokens": 9},
        }
    ]


def test_bad_bedrock_client_value_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_CLIENT", "nonsense")
    install(monkeypatch, groq=StubGroq("ok"))
    out = complete("s", "u", role="answer", max_tokens=5)
    assert out.provider == "groq"


def test_bedrock_failure_falls_back_to_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    mantle, groq = StubMantle(fail=Boom("404 model does not exist")), StubGroq("Kuala Lumpur")
    install(monkeypatch, mantle=mantle, groq=groq)
    out = complete("sys", "usr", role="answer", max_tokens=10)
    assert out == llm.LLMResult("Kuala Lumpur", "groq", "groq-answer-model", 20, 4)
    assert len(mantle.calls) == 1
    assert groq.calls == [
        {
            "model": "groq-answer-model",
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "usr"},
            ],
            "max_tokens": 10,
        }
    ]


def test_cooldown_skips_bedrock_then_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    mantle, groq = StubMantle(fail=Boom("down")), StubGroq()
    install(monkeypatch, mantle=mantle, groq=groq)
    assert preferred_provider("answer") == "bedrock"
    complete("s", "u", role="answer", max_tokens=5)
    assert len(mantle.calls) == 1
    assert preferred_provider("answer") == "groq"

    complete("s", "u", role="answer", max_tokens=5)
    advance(299)
    complete("s", "u", role="answer", max_tokens=5)
    assert len(mantle.calls) == 1, "Bedrock must not be tried during the cooldown"
    assert len(groq.calls) == 3

    advance(2)  # past the default 300 seconds
    assert preferred_provider("answer") == "bedrock"
    complete("s", "u", role="answer", max_tokens=5)
    assert len(mantle.calls) == 2


def test_cooldown_length_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BEDROCK_COOLDOWN", "10")
    mantle = StubMantle(fail=Boom("down"))
    install(monkeypatch, mantle=mantle, groq=StubGroq())
    complete("s", "u", role="tag", max_tokens=5)
    advance(11)
    complete("s", "u", role="tag", max_tokens=5)
    assert len(mantle.calls) == 2


def test_cooldown_is_per_role(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, mantle=StubMantle(fail=Boom("down")), groq=StubGroq())
    complete("s", "u", role="tag", max_tokens=5)
    assert preferred_provider("tag") == "groq"
    assert preferred_provider("answer") == "bedrock"


def test_cooldown_ignored_when_groq_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    mantle = StubMantle(fail=Boom("down"))
    install(monkeypatch, mantle=mantle, groq=StubGroq())
    complete("s", "u", role="tag", max_tokens=5)
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert preferred_provider("tag") == "bedrock"
    mantle.fail = None
    assert complete("s", "u", role="tag", max_tokens=5).provider == "bedrock"


def test_embed_fake_skips_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_FAKE", "1")
    groq = StubGroq("from groq")
    install(monkeypatch, groq=groq)  # building a Bedrock client would fail the test
    assert preferred_provider("tag") == "groq"
    out = complete("s", "u", role="tag", max_tokens=5)
    assert (out.provider, out.text) == ("groq", "from groq")
    assert llm._bedrock_down_until == {}


def test_embed_fake_without_groq_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_FAKE", "1")
    monkeypatch.setenv("GROQ_API_KEY", "")
    install(monkeypatch)
    with pytest.raises(LLMUnavailable, match="EMBED_FAKE"):
        complete("s", "u", role="tag", max_tokens=5)


def test_no_groq_key_and_bedrock_down_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "  ")
    install(monkeypatch, mantle=StubMantle(fail=Boom("no use case form")))
    with pytest.raises(LLMUnavailable, match="Boom: no use case form") as info:
        complete("s", "u", role="answer", max_tokens=5)
    assert "GROQ_API_KEY" in str(info.value)
    assert isinstance(info.value.__cause__, Boom)


def test_both_fail_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, mantle=StubMantle(fail=Boom("a")), groq=StubGroq(fail=Boom("b")))
    with pytest.raises(LLMUnavailable) as info:
        complete("s", "u", role="answer", max_tokens=5)
    assert "bedrock" in str(info.value) and "groq" in str(info.value)


def test_json_schema_uses_groq_json_mode_and_instruction(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = StubGroq('{"title": "t"}')
    install(monkeypatch, mantle=StubMantle(fail=Boom("down")), groq=groq)
    out = complete("sys", "usr", role="tag", max_tokens=100, json_schema=SCHEMA)
    assert out.text == '{"title": "t"}'
    call = groq.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    user = call["messages"][1]["content"]
    assert user.startswith("usr\n\n")
    assert user.endswith("Return only a JSON object with these keys: title, year.")


def test_no_json_schema_means_no_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = StubGroq()
    install(monkeypatch, mantle=StubMantle(fail=Boom("down")), groq=groq)
    complete("s", "u", role="answer", max_tokens=5)
    assert "response_format" not in groq.calls[0]
    assert groq.calls[0]["messages"][1]["content"] == "u"


def test_json_schema_instruction_also_reaches_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    mantle = StubMantle("{}")
    install(monkeypatch, mantle=mantle)
    complete("s", "u", role="tag", max_tokens=5, json_schema=SCHEMA)
    assert mantle.calls[0]["messages"][0]["content"].endswith("keys: title, year.")
    assert "output_config" not in mantle.calls[0]


def test_groq_reasoning_model_gets_low_effort_and_token_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_TAG_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("GROQ_ANSWER_MODEL", "openai/gpt-oss-120b")
    groq = StubGroq()
    install(monkeypatch, mantle=StubMantle(fail=Boom("down")), groq=groq)
    complete("s", "u", role="answer", max_tokens=10)
    complete("s", "u", role="tag", max_tokens=10)
    complete("s", "u", role="answer", max_tokens=5000)
    assert [c["max_tokens"] for c in groq.calls] == [2048, 1024, 5000]
    assert all(c["reasoning_effort"] == "low" for c in groq.calls)


def test_groq_reasoning_settings_also_apply_to_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_FAKE", "1")
    monkeypatch.setenv("GROQ_ANSWER_MODEL", "openai/gpt-oss-120b")
    groq = StubGroq()
    install(monkeypatch, groq=groq)
    list(stream("s", "u", role="answer", max_tokens=100))
    assert groq.calls[0]["max_tokens"] == 2048
    assert groq.calls[0]["reasoning_effort"] == "low"


def test_groq_other_models_get_no_reasoning_params(monkeypatch: pytest.MonkeyPatch) -> None:
    groq = StubGroq()
    install(monkeypatch, mantle=StubMantle(fail=Boom("down")), groq=groq)
    complete("s", "u", role="answer", max_tokens=10)
    assert groq.calls[0]["max_tokens"] == 10
    assert "reasoning_effort" not in groq.calls[0]


def test_default_groq_model_is_gpt_oss_120b(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_TAG_MODEL")
    monkeypatch.delenv("GROQ_ANSWER_MODEL")
    assert llm._model("groq", "tag") == "openai/gpt-oss-120b"
    assert llm._model("groq", "answer") == "openai/gpt-oss-120b"


# --- stream -------------------------------------------------------------------------------


def test_stream_bedrock_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mantle = StubMantle(deltas=["Hel", "lo"])
    install(monkeypatch, mantle=mantle, groq=StubGroq())
    result = stream("sys", "usr", role="answer", max_tokens=30)
    assert (result.provider, result.model) == ("bedrock", "bedrock-answer-model")
    assert list(result) == ["Hel", "lo"]
    assert mantle.calls[0]["max_tokens"] == 30


def test_stream_via_converse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_CLIENT", "converse")
    install(monkeypatch, converse=StubConverse())
    result = stream("sys", "usr", role="answer", max_tokens=30)
    assert result.provider == "bedrock"
    assert "".join(result) == "xy"


def test_stream_falls_back_before_first_token(monkeypatch: pytest.MonkeyPatch) -> None:
    # Failure on open, and failure as the very first thing the stream yields.
    for bedrock in (StubMantle(fail=Boom("404")), StubMantle(deltas=[Boom("first")])):
        monkeypatch.setattr(llm, "_bedrock_down_until", {})
        install(monkeypatch, mantle=bedrock, groq=StubGroq())
        result = stream("s", "u", role="answer", max_tokens=5)
        assert (result.provider, result.model) == ("groq", "groq-answer-model")
        assert list(result) == ["g1", "g2"]
        assert preferred_provider("answer") == "groq"


def test_stream_mid_stream_failure_raises_and_trips_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groq = StubGroq()
    install(monkeypatch, mantle=StubMantle(deltas=["one", Boom("cut off")]), groq=groq)
    result = stream("s", "u", role="answer", max_tokens=5)
    assert result.provider == "bedrock"
    seen: list[str] = []
    with pytest.raises(Boom):
        seen.extend(result)
    assert seen == ["one"]
    assert groq.calls == [], "no fallback after the first token"
    assert preferred_provider("answer") == "groq"


def test_stream_groq_only_when_bedrock_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_FAKE", "1")
    groq = StubGroq()
    install(monkeypatch, groq=groq)
    result = stream("s", "u", role="answer", max_tokens=5)
    assert result.provider == "groq"
    assert list(result) == ["g1", "g2"]
    assert groq.calls[0]["stream"] is True


def test_stream_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    install(monkeypatch, mantle=StubMantle(fail=Boom("down")))
    with pytest.raises(LLMUnavailable):
        stream("s", "u", role="answer", max_tokens=5)


def test_stream_close_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, mantle=StubMantle(deltas=["a", "b", "c"]))
    result = stream("s", "u", role="answer", max_tokens=5)
    assert next(iter(result)) == "a"  # the first token is not lost
    result.close()
    assert list(result) == []


# --- preferred_provider -------------------------------------------------------------------


def test_preferred_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    assert preferred_provider("answer") == "bedrock"
    monkeypatch.setenv("EMBED_FAKE", "1")
    assert preferred_provider("answer") == "groq"
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert preferred_provider("answer") == "groq", "nothing is available: report the small budget"
