# AGENTS.md

Shared instructions for every coding agent on this repo (Claude Code, Kiro, Cursor, Codex,
DeepSeek, anything else). Humans follow it too. `CLAUDE.md` just points here.

Sections marked TBD are filled in once the team confirms the decisions in `docs/BRAINSTORM.md`
section 7.

## What we are building

An intelligent document search and question-answering system for government agencies.
Documents (policies, SOPs, circulars, minutes, scanned letters) are ingested from a document
store, OCR'd and tagged, indexed with hybrid BM25 + vector search, and queried through a chat
UI that returns cited answers with page-level highlights. Bilingual (Bahasa Malaysia + English).

Read `docs/BRAINSTORM.md` for the why and `docs/PLAN.md` for who is doing what.

## Repo layout

```
contracts/     JSON Schema for every shared data shape and the API. SOURCE OF TRUTH.
engine/
  ingest/      Workstream A. File -> chunks with text, page, bbox, keywords, tags, embedding.
  index/       Workstream B. IndexStore interface, SqliteStore impl, hybrid search.
api/           Workstream C. FastAPI. /search, /ask, /documents.
web/           Workstream D. Next.js client.
samples/       Demo corpus (committed, small). Never put real agency documents here.
eval/          Question -> expected document pairs and the recall script.
docs/          Brainstorm, plan, demo script.
```

## Hard rules

1. **Contracts first.** If you need a new field, change `contracts/*.json` first, in its own
   commit, and tell the team. Never add an undocumented field to an API response.
2. **Stay in your lane.** A task says which package it touches. Do not edit other packages.
   If you need something from another package, write the call against its interface and leave
   a `TODO(<owner>)` comment.
3. **Page number is mandatory on every chunk.** Citations depend on it. A chunk without a
   page is a bug.
4. **No real government documents in the repo.** Synthetic samples only.
5. **No secrets in code.** AWS credentials come from the environment or an AWS profile.
   `.env` is gitignored; `.env.example` is committed.
6. **Bedrock calls are cached or batched.** Embeddings cached by content hash. Tagging runs
   once per document. Do not call a model inside a loop over chunks without batching.
7. **Tests next to code.** `engine/ingest/chunker.py` has `engine/ingest/test_chunker.py`.
   Write the test first for [A] tasks.

## Stack (confirmed)

- Language: Python 3.11 for `engine/` and `api/`, TypeScript for `web/`.
- Backend: FastAPI + pydantic v2. Frontend: Next.js 14 app router + Tailwind.
- PDF: PyMuPDF (`fitz`) for text, blocks, bboxes, and page rendering. Not pypdf, not poppler.
- Index store: `SqliteStore` (SQLite + rank_bm25 + numpy, in-process) behind the
  `IndexStore` interface in `engine/index/store.py`. pgvector is a stretch swap, same interface.
- AWS: S3 (uploads, optional), Textract (OCR, stretch), Bedrock.
  - Embeddings: `amazon.titan-embed-text-v2:0` via boto3 `bedrock-runtime`, 1024 dims.
  - Tagging and answers: Claude on Bedrock through the `anthropic` SDK's
    `AnthropicBedrockMantle(aws_region=...)` client. Model IDs from `.env`
    (`BEDROCK_TAG_MODEL`, `BEDROCK_ANSWER_MODEL`), Bedrock IDs carry the `anthropic.` prefix.
    Confirm model access in the Bedrock console for the region before relying on an ID.
  - Region: from `.env` `AWS_REGION`. Default `ap-southeast-1`.
- Package management: `uv` for Python, `pnpm` for web.

## Conventions

- Python: `ruff` format + lint, type hints everywhere, pydantic models for anything crossing
  a package boundary. Functions over classes unless state is needed.
- TypeScript: strict mode, API types generated from `contracts/` (do not hand-write them).
- Commits: `<area>: <what>` e.g. `ingest: add YAKE keyword extraction`. Small and often.
- Branches: `<name>/<workstream><task>` e.g. `law/A4-chunker`. PR to `main`, one reviewer.
- Language codes: `ms` for Malay, `en` for English. Store on every chunk as `lang`.
- IDs: `doc_id` is sha256 of file bytes (first 16 hex chars). `chunk_id` is `{doc_id}:{page}:{n}`.

## Running things

```
uv sync --extra dev
cp .env.example .env               # then fill in AWS_PROFILE / AWS_REGION
uv run python -m engine.ingest samples/   # ingest the demo corpus
uv run uvicorn api.main:app --reload
cd web && pnpm dev
uv run pytest                      # all python tests
```

## How to work on a task from docs/PLAN.md

1. Read the task row and its "done when".
2. Read the relevant file(s) in `contracts/`.
3. Write the test. Make it fail. Make it pass. Run the full test suite.
4. Report the diff and the test output. Do not merge your own work.
