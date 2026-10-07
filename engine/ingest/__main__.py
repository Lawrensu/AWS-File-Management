"""A6 CLI. `python -m engine.ingest <folder>` ingests every PDF, then resolves supersession."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from engine.index.store import IndexStore, SqliteStore
from engine.index.supersession import resolve_supersession
from engine.ingest.pipeline import ingest_file


def main(argv: list[str] | None = None, store: IndexStore | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(prog="python -m engine.ingest")
    parser.add_argument("folder", help="folder of PDFs to ingest")
    parser.add_argument(
        "--force", action="store_true", help="re-ingest files already in the index"
    )
    args = parser.parse_args(argv)

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"error: {folder} is not a folder", file=sys.stderr)
        return 2
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")

    own_store = store is None
    if store is None:
        store = SqliteStore(os.environ.get("INDEX_PATH", "data/index.sqlite"))
    failed = 0
    no_embeddings = 0
    scanned_skipped = 0
    try:
        for f in files:
            try:
                r = ingest_file(f, store, force=args.force)
            except Exception as exc:  # noqa: BLE001 - one bad PDF must not stop the run
                failed += 1
                print(f"failed {f.name}: {exc}")
                continue
            no_embeddings += r.embedding_failed
            scanned_skipped += r.scanned_pages_skipped
            verb = "skipped" if r.skipped else "ingested"
            print(f"{verb} {f.name}  pages={r.pages} chunks={r.chunks}")

        pairs = resolve_supersession(store)  # once, after every file is in
        titles = {d["doc_id"]: d["title"] for d in store.list_documents()}
        for old, new in pairs:
            print(f"superseded: {titles.get(old, old)} -> {titles.get(new, new)}")
        docs, chunks = store.count()
        print(f"documents: {docs}, chunks: {chunks}")
        if no_embeddings or scanned_skipped:
            print(
                f"warnings: {no_embeddings} files with no embeddings, "
                f"{scanned_skipped} scanned pages skipped"
            )
    finally:
        if own_store and isinstance(store, SqliteStore):
            store.close()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
