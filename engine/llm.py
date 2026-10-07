"""The one LLM entry point. Every model call in this repo goes through complete() or stream().

Provider order is Bedrock first, then Groq. Bedrock is skipped when EMBED_FAKE=1 (that flag
means no AWS on this machine) and while its circuit breaker is open. Groq is skipped when
GROQ_API_KEY is empty. If nothing is left to try, or everything tried failed, LLMUnavailable
is raised and the caller decides what to fall back to.

Bedrock client, chosen by BEDROCK_CLIENT:
- "mantle" (default): the anthropic SDK's AnthropicBedrockMantle(aws_region=AWS_REGION).
- "converse": boto3 bedrock-runtime converse and converse_stream.

Circuit breaker: after a Bedrock failure for a role, Bedrock is skipped for that role for
LLM_BEDROCK_COOLDOWN seconds (default 300), so calls do not each pay the failure latency.
When Groq is not available the cooldown is ignored, because there is nothing else to try.

Models and the region are read from the environment on every call: BEDROCK_TAG_MODEL,
BEDROCK_ANSWER_MODEL, GROQ_TAG_MODEL, GROQ_ANSWER_MODEL, AWS_REGION. The DEFAULT_* constants
below are only the values used when a variable is unset, and match .env.example.
"""

from __future__ import annotations

import functools
import logging
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

ROLES = ("tag", "answer")
DEFAULT_REGION = "ap-southeast-1"
DEFAULT_COOLDOWN_SECONDS = 300.0
DEFAULT_BEDROCK_MODELS = {
    "tag": "anthropic.claude-haiku-4-5",
    "answer": "anthropic.claude-sonnet-5-5",
}
DEFAULT_GROQ_MODELS = {
    "tag": "openai/gpt-oss-120b",
    "answer": "openai/gpt-oss-120b",
}
# gpt-oss models reason before they answer, and reasoning tokens count against max_tokens. They
# run at low reasoning effort, and max_tokens never goes below this floor so the visible answer
# is not cut off by the reasoning.
GROQ_REASONING_PREFIXES = ("openai/gpt-oss",)
GROQ_MIN_TOKENS = {"tag": 1024, "answer": 2048}


class LLMUnavailable(RuntimeError):
    """No provider could answer: none is available, or every one that was tried failed."""


@dataclass
class LLMResult:
    text: str
    provider: str  # "bedrock" or "groq"
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class StreamResult:
    """Iterate to get text deltas. .provider and .model say who is actually answering."""

    def __init__(self, provider: str, model: str, deltas: Iterator[str]) -> None:
        self.provider = provider
        self.model = model
        self._deltas = deltas

    def __iter__(self) -> Iterator[str]:
        return self._deltas

    def close(self) -> None:
        closer = getattr(self._deltas, "close", None)
        if closer is not None:
            closer()


# --- public API ---------------------------------------------------------------------------


def complete(
    system: str,
    user: str,
    *,
    role: str,
    max_tokens: int,
    json_schema: dict | None = None,
) -> LLMResult:
    """One non-streaming call. Tries each available provider in order.

    With json_schema, the user message gets a one-line instruction to return only JSON with the
    schema's keys, and Groq runs in JSON mode. The schema is not sent to Bedrock as a native
    structured-output request; the instruction is what asks for JSON there, so callers must
    still parse and validate the text.
    """
    _check_role(role)
    if json_schema is not None:
        user = f"{user}\n\n{_json_instruction(json_schema)}"
    providers, skipped = _plan(role)
    errors: list[str] = []
    last: Exception | None = None
    for provider in providers:
        model = _model(provider, role)
        try:
            if provider == "bedrock":
                result = _bedrock_complete(model, system, user, max_tokens)
            else:
                result = _groq_complete(
                    model, role, system, user, max_tokens, json_schema is not None
                )
        except Exception as exc:  # noqa: BLE001 - any provider failure means try the next one
            last = exc
            errors.append(_describe(provider, model, exc))
            _on_failure(provider, role, model, exc)
            continue
        return result
    raise _unavailable(skipped, errors) from last


def stream(system: str, user: str, *, role: str, max_tokens: int) -> StreamResult:
    """A streaming call. Returns once the first token has arrived, so .provider and .model are
    the provider that is really answering.

    Falling back to the next provider is only possible before the first token. If the stream
    fails after that, the provider's exception is raised from the iteration.
    """
    _check_role(role)
    providers, skipped = _plan(role)
    errors: list[str] = []
    last: Exception | None = None
    for provider in providers:
        model = _model(provider, role)
        deltas = _watch(
            provider, role, model, _open_stream(provider, role, model, system, user, max_tokens)
        )
        try:
            first = next(deltas)
        except StopIteration:
            return StreamResult(provider, model, iter(()))
        except Exception as exc:  # noqa: BLE001 - failed before the first token, try the next
            last = exc
            errors.append(_describe(provider, model, exc))
            continue
        return StreamResult(provider, model, _prepend(first, deltas))
    raise _unavailable(skipped, errors) from last


def preferred_provider(role: str) -> str:
    """The provider the next call will try first: "bedrock" or "groq".

    /ask uses this to send 8 chunks to Bedrock or 5 to Groq. When no provider is available at
    all it returns "groq", the smaller budget, and the call itself will raise LLMUnavailable.
    """
    _check_role(role)
    providers, _ = _plan(role)
    return providers[0] if providers else "groq"


# --- provider order and circuit breaker ---------------------------------------------------

_bedrock_down_until: dict[str, float] = {}


def _now() -> float:
    return time.monotonic()


def _cooldown() -> float:
    raw = os.environ.get("LLM_BEDROCK_COOLDOWN", "").strip()
    try:
        return float(raw) if raw else DEFAULT_COOLDOWN_SECONDS
    except ValueError:
        return DEFAULT_COOLDOWN_SECONDS


def _groq_available() -> bool:
    return bool(os.environ.get("GROQ_API_KEY", "").strip())


def _plan(role: str) -> tuple[list[str], list[str]]:
    """(providers to try in order, reasons for the ones skipped)."""
    providers: list[str] = []
    skipped: list[str] = []
    groq = _groq_available()
    if os.environ.get("EMBED_FAKE") == "1":
        skipped.append("Bedrock skipped: EMBED_FAKE=1")
    elif groq and _now() < _bedrock_down_until.get(role, 0.0):
        skipped.append("Bedrock skipped: cooling down after a failure")
    else:
        providers.append("bedrock")
    if groq:
        providers.append("groq")
    else:
        skipped.append("Groq skipped: GROQ_API_KEY is empty")
    return providers, skipped


def _on_failure(provider: str, role: str, model: str, exc: Exception) -> None:
    if provider == "bedrock":
        _bedrock_down_until[role] = _now() + _cooldown()
    log.warning("llm: %s", _describe(provider, model, exc))


def _describe(provider: str, model: str, exc: Exception) -> str:
    return f"{provider} {model} failed with {type(exc).__name__}: {exc}"


def _unavailable(skipped: list[str], errors: list[str]) -> LLMUnavailable:
    return LLMUnavailable("; ".join(skipped + errors) or "no LLM provider available")


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, got {role!r}")


def _model(provider: str, role: str) -> str:
    if provider == "bedrock":
        return os.environ.get(f"BEDROCK_{role.upper()}_MODEL") or DEFAULT_BEDROCK_MODELS[role]
    return os.environ.get(f"GROQ_{role.upper()}_MODEL") or DEFAULT_GROQ_MODELS[role]


def _json_instruction(schema: dict) -> str:
    keys = list((schema.get("properties") or {}).keys())
    if not keys:
        return "Return only valid JSON."
    return f"Return only a JSON object with these keys: {', '.join(keys)}."


# --- streaming plumbing -------------------------------------------------------------------


def _open_stream(
    provider: str, role: str, model: str, system: str, user: str, max_tokens: int
) -> Iterator[str]:
    if provider == "bedrock":
        return _bedrock_stream(model, system, user, max_tokens)
    return _groq_stream(model, role, system, user, max_tokens)


def _watch(provider: str, role: str, model: str, deltas: Iterator[str]) -> Iterator[str]:
    """Pass deltas through, and record a Bedrock failure in the breaker, wherever it happens."""
    try:
        yield from deltas
    except Exception as exc:  # recorded, then re-raised for the caller
        _on_failure(provider, role, model, exc)
        raise
    finally:
        closer = getattr(deltas, "close", None)
        if closer is not None:
            closer()


def _prepend(first: str, rest: Iterator[str]) -> Iterator[str]:
    try:
        yield first
        yield from rest
    finally:
        closer = getattr(rest, "close", None)
        if closer is not None:
            closer()


# --- Bedrock ------------------------------------------------------------------------------


def _bedrock_client_kind() -> str:
    kind = os.environ.get("BEDROCK_CLIENT", "mantle").strip().lower() or "mantle"
    if kind not in ("mantle", "converse"):
        raise ValueError(f"BEDROCK_CLIENT must be 'mantle' or 'converse', got {kind!r}")
    return kind


def _region() -> str:
    return os.environ.get("AWS_REGION") or DEFAULT_REGION


@functools.cache
def _mantle_client(region: str) -> Any:
    from anthropic import AnthropicBedrockMantle

    return AnthropicBedrockMantle(aws_region=region)


@functools.cache
def _converse_client(region: str) -> Any:
    import boto3

    return boto3.client("bedrock-runtime", region_name=region)


def _bedrock_complete(model: str, system: str, user: str, max_tokens: int) -> LLMResult:
    if _bedrock_client_kind() == "mantle":
        resp = _mantle_client(_region()).messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        usage = getattr(resp, "usage", None)
        return LLMResult(
            text,
            "bedrock",
            model,
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
        )
    resp = _converse_client(_region()).converse(
        modelId=model,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens},
    )
    blocks = resp["output"]["message"]["content"]
    text = "".join(b["text"] for b in blocks if "text" in b)
    usage = resp.get("usage") or {}
    return LLMResult(text, "bedrock", model, usage.get("inputTokens"), usage.get("outputTokens"))


def _bedrock_stream(model: str, system: str, user: str, max_tokens: int) -> Iterator[str]:
    if _bedrock_client_kind() == "mantle":
        client = _mantle_client(_region())
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as events:
            yield from events.text_stream
        return
    resp = _converse_client(_region()).converse_stream(
        modelId=model,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens},
    )
    for event in resp["stream"]:
        text = event.get("contentBlockDelta", {}).get("delta", {}).get("text")
        if text:
            yield text


# --- Groq ---------------------------------------------------------------------------------


@functools.cache
def _groq_client(api_key: str) -> Any:
    from groq import Groq

    return Groq(api_key=api_key)


def _groq_messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _groq_params(model: str, role: str, max_tokens: int) -> dict[str, Any]:
    """max_tokens, plus low reasoning effort and a token floor for reasoning models."""
    if model.startswith(GROQ_REASONING_PREFIXES):
        return {
            "max_tokens": max(max_tokens, GROQ_MIN_TOKENS[role]),
            "reasoning_effort": "low",
        }
    return {"max_tokens": max_tokens}


def _groq_complete(
    model: str, role: str, system: str, user: str, max_tokens: int, json_mode: bool
) -> LLMResult:
    kwargs: dict[str, Any] = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _groq_client(os.environ["GROQ_API_KEY"].strip()).chat.completions.create(
        model=model,
        messages=_groq_messages(system, user),
        **_groq_params(model, role, max_tokens),
        **kwargs,
    )
    usage = getattr(resp, "usage", None)
    return LLMResult(
        resp.choices[0].message.content or "",
        "groq",
        model,
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )


def _groq_stream(model: str, role: str, system: str, user: str, max_tokens: int) -> Iterator[str]:
    chunks = _groq_client(os.environ["GROQ_API_KEY"].strip()).chat.completions.create(
        model=model,
        messages=_groq_messages(system, user),
        **_groq_params(model, role, max_tokens),
        stream=True,
    )
    for chunk in chunks:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
