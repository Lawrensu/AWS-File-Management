"""B4. Retrieval eval: recall@5 of hybrid_search over eval/questions.json.

    uv run python eval/run.py --bm25-only   # no AWS needed
    uv run python eval/run.py               # embeds the questions with Titan (A3)

questions.json is a list of {"question": str, "expected_filename": str}. Filenames are
compared by stem, so a manifest's "01-x.md" matches the indexed "01-x.pdf".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from engine.index.hybrid import Filters, hybrid_search
from engine.index.store import SqliteStore

TOP_K = 5
QUESTIONS = Path(__file__).with_name("questions.json")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Print recall@5 of hybrid search.")
    parser.add_argument("--bm25-only", action="store_true", help="skip embeddings, no AWS")
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--index", default=os.environ.get("INDEX_PATH", "data/index.sqlite"))
    args = parser.parse_args(argv)

    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    if not questions:
        print(f"No questions in {args.questions}.", file=sys.stderr)
        return 1
    store = SqliteStore(args.index)
    n_docs, n_chunks = store.count()
    if n_chunks == 0:
        print(
            f"Index {args.index} is empty. Run: uv run python -m engine.ingest samples/",
            file=sys.stderr,
        )
        return 1

    vectors: list[np.ndarray | None] = [None] * len(questions)
    if not args.bm25_only:
        try:
            vectors = list(_embed([q["question"] for q in questions]))
        except Exception as e:  # noqa: BLE001 - any Bedrock failure ends the run the same way
            print(
                f"Embedding failed ({e}). Fix AWS credentials or pass --bm25-only.", file=sys.stderr
            )
            return 1
    mode = "BM25 only" if vectors[0] is None else "hybrid"
    print(f"{len(questions)} questions, {n_docs} documents, {n_chunks} chunks, {mode}\n")

    filenames = {d["doc_id"]: d.get("filename") or "" for d in store.list_documents()}
    hits = 0
    for q, vec in zip(questions, vectors):
        results = hybrid_search(store, q["question"], vec, Filters(), top_k=TOP_K)
        got = [filenames.get(r["doc_id"], "") for r in results]
        rank = next(
            (i for i, f in enumerate(got, 1) if _same_file(f, q["expected_filename"])), None
        )
        hits += rank is not None
        top = got[0] if got else "-"
        miss = "" if rank else f"  (expected {q['expected_filename']})"
        print(f"{f'HIT@{rank}' if rank else 'MISS':6} {top:45} {q['question']}{miss}")
    print(f"\nrecall@{TOP_K} = {hits}/{len(questions)} ({100 * hits / len(questions):.0f}%)")
    return 0


def _embed(texts: list[str]) -> list[np.ndarray | None]:
    """One batched call for every question. BM25 only when embeddings are fake or absent."""
    if os.environ.get("EMBED_FAKE") == "1":
        print("EMBED_FAKE=1: fake vectors are noise, running BM25 only.", file=sys.stderr)
        return [None] * len(texts)
    try:
        from engine.ingest.embed import embed_texts
    except ImportError:
        # TODO(A3): engine.ingest.embed.embed_texts
        print("engine.ingest.embed is not there yet, running BM25 only.", file=sys.stderr)
        return [None] * len(texts)
    return list(embed_texts(texts))


def _same_file(got: str, expected: str) -> bool:
    return bool(got) and Path(got).stem.lower() == Path(expected).stem.lower()


if __name__ == "__main__":
    sys.exit(main())
