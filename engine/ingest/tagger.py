"""A4. Tag a document with Claude Haiku on Bedrock. Never raises; falls back instead.

The prompt lives in engine/ingest/prompts/tagger.md and is read from there at first use.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).with_name("prompts") / "tagger.md"
TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "contracts" / "taxonomy.json"
DEFAULT_MODEL = "anthropic.claude-haiku-4-5"
MAX_INPUT_CHARS = 6000
MAX_TOPICS = 3
RETRY_PREFIX = "Your previous output was not valid JSON. Output only the JSON object."
LANGS = ("ms", "en", "mixed")

_FENCE = re.compile(r"```[^\n]*\n(.*?)\n```", re.DOTALL)


def fallback(filename: str) -> dict[str, Any]:
    """The tags used when the model is unavailable or its output is unusable."""
    return {
        "title": filename,
        "doc_type": "other",
        "department": "Umum",
        "topics": ["lain"],
        "year": None,
        "lang": None,  # None tells the pipeline to use detect_lang
        "supersedes": [],
        "summary": "",
    }


def tag_document(filename: str, text: str) -> dict[str, Any]:
    """Return title, doc_type, department, topics, year, lang, supersedes, summary.

    One model call per document, two if the first reply is not valid JSON.
    """
    try:
        if not text.strip():
            return fallback(filename)
        system, user_template = _prompts()
        user = (
            user_template.replace("{{taxonomy}}", _taxonomy_text())
            .replace("{{filename}}", filename)
            .replace("{{text}}", text[:MAX_INPUT_CHARS])
        )
        client = _client()
        model = os.environ.get("BEDROCK_TAG_MODEL", DEFAULT_MODEL)
        parsed = _parse(_call(client, model, system, user))
        if parsed is None:
            log.warning("tagger: invalid JSON for %s, retrying once", filename)
            parsed = _parse(_call(client, model, system, f"{RETRY_PREFIX}\n\n{user}"))
        if parsed is None:
            log.warning("tagger: invalid JSON twice for %s, using fallback tags", filename)
            return fallback(filename)
        return _validate(parsed, filename)
    except Exception as exc:  # noqa: BLE001 - tagging must never fail ingest
        log.warning("tagger: %s for %s, using fallback tags", exc, filename)
        return fallback(filename)


def _client() -> Any:
    from anthropic import AnthropicBedrockMantle

    return AnthropicBedrockMantle(aws_region=os.environ.get("AWS_REGION", "ap-southeast-1"))


def _call(client: Any, model: str, system: str, user: str) -> str:
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


@functools.cache
def _prompts() -> tuple[str, str]:
    """(system, user template): the first fenced block under ## System and under ## User."""
    md = PROMPT_PATH.read_text(encoding="utf-8")
    return _first_block(md, "## System"), _first_block(md, "## User")


def _first_block(md: str, header: str) -> str:
    start = md.index(header) + len(header)
    m = _FENCE.search(md, start)
    if m is None:
        raise ValueError(f"no fenced block under {header} in {PROMPT_PATH}")
    return m.group(1).strip()


@functools.cache
def _taxonomy_text() -> str:
    return TAXONOMY_PATH.read_text(encoding="utf-8")


@functools.cache
def _taxonomy() -> dict[str, list[str]]:
    return json.loads(_taxonomy_text())


def _parse(raw: str) -> dict[str, Any] | None:
    s = raw.strip()
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _validate(raw: dict[str, Any], filename: str) -> dict[str, Any]:
    tax = _taxonomy()
    out = fallback(filename)

    def replaced(field: str, value: Any, to: Any) -> None:
        log.warning("tagger: %s=%r not allowed for %s, using %r", field, value, filename, to)

    title = raw.get("title")
    if isinstance(title, str) and title.strip():
        out["title"] = title.strip()

    for field, key in (("doc_type", "doc_type"), ("department", "department")):
        value = raw.get(field)
        if value in tax[key]:
            out[field] = value
        else:
            replaced(field, value, out[field])

    topics = raw.get("topics")
    kept: list[str] = []
    for t in topics if isinstance(topics, list) else []:
        if t in tax["topic"] and t not in kept:
            kept.append(t)
        elif t not in tax["topic"]:
            replaced("topics", t, None)
    out["topics"] = kept[:MAX_TOPICS] or ["lain"]

    year = raw.get("year")
    if isinstance(year, int) and not isinstance(year, bool):
        out["year"] = year
    elif isinstance(year, str) and year.strip().isdigit():
        out["year"] = int(year.strip())

    lang = raw.get("lang")
    out["lang"] = lang if lang in LANGS else None

    supersedes = raw.get("supersedes")
    if isinstance(supersedes, list):
        out["supersedes"] = [s.strip() for s in supersedes if isinstance(s, str) and s.strip()]

    summary = raw.get("summary")
    out["summary"] = summary if isinstance(summary, str) else ""
    return out
