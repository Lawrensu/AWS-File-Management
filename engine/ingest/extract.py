"""A1. PDF to pages with text blocks, bboxes, and a scanned flag."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# `import fitz` is deprecated in PyMuPDF 1.28 and prints a warning; same library, same API.
import pymupdf as fitz

SCANNED_MIN_CHARS = 50


@dataclass
class Block:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points, origin top-left


@dataclass
class Page:
    number: int  # 1-indexed
    text: str  # full page text, blocks joined with "\n"
    blocks: list[Block]
    is_scanned: bool  # True when len(text.strip()) < 50
    width: float
    height: float


def extract_pages(path: str | Path) -> list[Page]:
    pages: list[Page] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc):
            blocks: list[Block] = []
            # (x0, y0, x1, y1, text, block_no, block_type); type 0 is text, 1 is image.
            for x0, y0, x1, y1, text, _no, block_type in page.get_text("blocks"):
                text = text.strip()
                if block_type != 0 or not text:
                    continue
                blocks.append(Block(text, (float(x0), float(y0), float(x1), float(y1))))
            blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
            text = "\n".join(b.text for b in blocks)
            pages.append(
                Page(
                    number=index + 1,
                    text=text,
                    blocks=blocks,
                    is_scanned=len(text.strip()) < SCANNED_MIN_CHARS,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                )
            )
    return pages
