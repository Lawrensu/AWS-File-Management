"""A2. Pages to chunk dicts (contracts/chunk.schema.json). Never merges across pages."""

from __future__ import annotations

import re
from typing import Any

from engine.ingest.extract import Block, Page

HEADING_MAX_WORDS = 12
_HEADING_PREFIX = re.compile(r"^(?:\d+\.(?:\d+\.?)*|BAHAGIAN\b|PART\b|SEKSYEN\b)")


def chunk_pages(
    doc_id: str, pages: list[Page], max_tokens: int = 800, overlap: int = 100
) -> list[dict[str, Any]]:
    """Split each page into windows of max_tokens whitespace words, overlapping by overlap.

    lang is "en" and embedding None here; the pipeline overwrites both.
    """
    if not 0 <= overlap < max_tokens:
        raise ValueError(f"need 0 <= overlap < max_tokens, got {overlap=} {max_tokens=}")
    step = max_tokens - overlap
    chunks: list[dict[str, Any]] = []
    last_heading: str | None = None  # carried across pages as metadata only

    for page in pages:
        if not page.text.strip():
            continue
        words: list[str] = []
        block_of: list[int] = []  # block index of each word
        for i, block in enumerate(page.blocks):
            ws = block.text.split()
            words.extend(ws)
            block_of.extend([i] * len(ws))
        if not words:
            continue

        headings = _headings_by_block(page.blocks, last_heading)
        n, start = 0, 0
        while True:
            window = words[start : start + max_tokens]
            first_block = block_of[start]
            chunks.append(
                {
                    "chunk_id": f"{doc_id}:{page.number}:{n}",
                    "doc_id": doc_id,
                    "page": page.number,
                    "bbox": [float(v) for v in page.blocks[first_block].bbox],
                    "heading": headings[first_block],
                    "text": " ".join(window),
                    "lang": "en",
                    "source": "native",
                    "embedding": None,
                }
            )
            n += 1
            if start + max_tokens >= len(words):
                break
            start += step
        last_heading = headings[-1]
    return chunks


def _headings_by_block(blocks: list[Block], carried: str | None) -> list[str | None]:
    """For each block, the last heading at or before it, starting from the carried heading."""
    out: list[str | None] = []
    current = carried
    for block in blocks:
        text = " ".join(block.text.split())
        if _is_heading(text):
            current = text
        out.append(current)
    return out


def _is_heading(text: str) -> bool:
    if not text or len(text.split()) >= HEADING_MAX_WORDS:
        return False
    return text.isupper() or bool(_HEADING_PREFIX.match(text))
