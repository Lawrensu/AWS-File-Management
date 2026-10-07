"""C3. POST /ask. Prompt and post-processing rules live in api/prompts/answer.md.

Every model call goes through engine.llm.stream. One call per question, never per chunk.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from langdetect import DetectorFactory, LangDetectException, detect

from api.deps import Store, query_vector, to_filters
from api.models import AskRequest, AskResponse, Citation
from engine.index.hybrid import hybrid_search
from engine.index.store import IndexStore
from engine.llm import LLMUnavailable, preferred_provider, stream

DetectorFactory.seed = 0
log = logging.getLogger("api.ask")
router = APIRouter()

PROMPT_PATH = Path(__file__).parent / "prompts" / "answer.md"
MAX_TOKENS = 1500
CHUNKS = {"bedrock": 8, "groq": 5}
QUOTE_CHARS = 200
# RRF with k=60: rank 1 in both lists scores 2/61 = 0.0328, rank 1 in one list 1/61 = 0.0164.
# BM25-only scores are about half of hybrid ones, so the bar is halved without vectors.
# Starting guesses from answer.md; tune after the eval run.
HIGH_CONFIDENCE_HYBRID = 0.03
HIGH_CONFIDENCE_BM25 = 0.015
NOT_FOUND = {
    "ms": "Tidak dijumpai dalam dokumen yang tersedia.",
    "en": "Not found in the available documents.",
}
# Sent with every question: models follow the excerpt language over rule 1 of the system prompt.
ANSWER_IN = {"ms": "Answer in Bahasa Malaysia.", "en": "Answer in English."}
_MARKER = re.compile(r"\[(\d+)\]")
# Short Malay questions often confuse langdetect, so common Malay words decide first.
_MALAY_WORDS = {
    "apa", "apakah", "berapa", "berapakah", "bagaimana", "bagaimanakah", "siapa", "bila",
    "bilakah", "adakah", "boleh", "yang", "dan", "untuk", "bagi", "dalam", "kepada", "saya",
    "kadar", "elaun", "tuntutan", "cuti", "perolehan", "pegawai", "jabatan", "mesyuarat",
}


def _system_prompt() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    section = text.split("## System", 1)[1]
    return section.split("```", 2)[1].strip()


SYSTEM = _system_prompt()


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, store: Store):
    language = question_language(req.question)
    query_vec = query_vector(req.question)
    k = CHUNKS.get(preferred_provider("answer"), CHUNKS["groq"])
    hits = hybrid_search(store, req.question, query_vec, to_filters(req.filters), top_k=k)
    excerpts = [_excerpt(store, hit) for hit in hits]
    threshold = HIGH_CONFIDENCE_HYBRID if query_vec is not None else HIGH_CONFIDENCE_BM25

    if not excerpts:
        # Nothing to ground an answer in, so skip the model call entirely.
        result = _not_found(language)
        if req.stream:
            return _sse(iter(()), lambda _: result, {})
        return result

    try:
        answer_stream = stream(
            SYSTEM,
            build_user_prompt(req.question, excerpts, language),
            role="answer",
            max_tokens=MAX_TOKENS,
        )
    except LLMUnavailable as exc:
        log.warning("answer model unavailable: %s", exc)
        return JSONResponse(status_code=503, content={"error": f"answer model unavailable: {exc}"})

    log.info("answer via %s %s, %d excerpts", answer_stream.provider, answer_stream.model, k)
    headers = {"X-Rujuk-Provider": answer_stream.provider, "X-Rujuk-Model": answer_stream.model}

    def finish(text: str) -> AskResponse:
        return build_response(text, excerpts, language, hits[0]["score"], threshold)

    if req.stream:
        return _sse(_safe(answer_stream), finish, headers)
    text = "".join(_safe(answer_stream))
    return JSONResponse(content=finish(text).model_dump(), headers=headers)


def question_language(question: str) -> str:
    """"ms" or "en" for the answer, per answer.md: langdetect forced to the two languages."""
    words = set(re.findall(r"\w+", question.lower()))
    if words & _MALAY_WORDS:
        return "ms"
    try:
        lang = detect(question)
    except LangDetectException:
        return "ms"
    return "ms" if lang in ("ms", "id") else "en"


def build_user_prompt(question: str, excerpts: list[dict], language: str) -> str:
    blocks = [
        f"[{i}] {e['title']} | page {e['page']} | {e['status_label']}\n{e['text']}"
        for i, e in enumerate(excerpts, 1)
    ]
    return (
        "Excerpts:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}\n{ANSWER_IN[language]}"
    )


def build_response(
    text: str, excerpts: list[dict], language: str, top_score: float, threshold: float
) -> AskResponse:
    answer = text.strip()
    if _is_not_found(answer):
        return _not_found(language, answer)

    citations: list[Citation] = []
    seen: set[int] = set()
    for match in _MARKER.finditer(answer):
        n = int(match.group(1))
        if n in seen or not 1 <= n <= len(excerpts):
            continue
        seen.add(n)
        e = excerpts[n - 1]
        citations.append(
            Citation(
                n=n,
                chunk_id=e["chunk_id"],
                doc_id=e["doc_id"],
                title=e["title"],
                page=e["page"],
                status=e["status"],
                quote=e["text"][:QUOTE_CHARS],
            )
        )
    return AskResponse(
        answer=answer,
        language=language,
        confidence="high" if top_score >= threshold else "medium",
        citations=citations,
        not_found=False,
    )


def _excerpt(store: IndexStore, hit: dict) -> dict:
    chunk = store.get_chunk(hit["chunk_id"]) or {}
    text = " ".join((chunk.get("text") or hit["snippet"]).split())
    label = "CURRENT"
    if hit["status"] == "superseded":
        newer = store.get_document(hit["superseded_by"]) if hit["superseded_by"] else None
        label = f"SUPERSEDED by {newer['title']}" if newer else "SUPERSEDED"
    return {**hit, "text": text, "status_label": label}


def _is_not_found(answer: str) -> bool:
    cleaned = answer.strip().strip("\"'").strip()
    return cleaned in NOT_FOUND.values()


def _not_found(language: str, answer: str | None = None) -> AskResponse:
    return AskResponse(
        answer=answer or NOT_FOUND[language],
        language=language,
        confidence="low",
        citations=[],
        not_found=True,
    )


def _safe(deltas) -> Iterator[str]:
    """Yield deltas; a failure after the first token ends the answer instead of the request."""
    try:
        yield from deltas
    except Exception as exc:  # noqa: BLE001 - mid-stream provider failure
        log.warning("answer stream broke: %s", type(exc).__name__)
    finally:
        close = getattr(deltas, "close", None)
        if close is not None:
            close()


def _sse(deltas: Iterator[str], finish, headers: dict[str, str]) -> StreamingResponse:
    def events() -> Iterator[str]:
        parts: list[str] = []
        for delta in deltas:
            parts.append(delta)
            yield _event({"type": "token", "text": delta})
        yield _event({"type": "done", "answer": finish("".join(parts)).model_dump()})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", **headers},
    )


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
