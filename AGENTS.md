# AGENTS.md

Rules for every coding agent and every human on this repo. `CLAUDE.md` and
`.kiro/steering/project.md` point here.

## What we are building

Rujuk: document search and question answering for government agencies. Documents are
ingested, OCR'd if scanned, tagged, indexed with hybrid BM25 + vector search, and queried
through a chat UI that returns cited answers with page highlights. Bilingual Malay and
English. Why: `docs/BRAINSTORM.md`. Who does what: `docs/PLAN.md`.

## Layout

- `contracts/` JSON schemas and the API contract. Source of truth for every shared shape.
- `engine/ingest/` A. File to chunks with text, page, bbox, keywords, tags, embedding.
- `engine/index/` B. `IndexStore` interface, `SqliteStore`, hybrid search, supersession.
- `engine/testing.py` `FakeStore` and fixtures. Every test uses these, never `SqliteStore`.
- `api/` C. FastAPI: `/search`, `/ask`, `/documents`.
- `web/` D. Next.js client.
- `samples/` synthetic seed corpus. `eval/` retrieval questions and runner.
- `docs/` brainstorm, plan, agent prompts, demo script.

## Rules

- Contracts first. A new field goes into `contracts/` in its own commit, and you tell the
  team. No undocumented fields in API responses.
- Stay in your package. Need something from another package? Call its interface and leave
  a `TODO(<letter>)`.
- Every chunk has a page number. No exceptions.
- No real government documents in the repo.
- No secrets in code. `.env` is gitignored, `.env.example` is committed.
- Bedrock calls are cached or batched. Never call a model inside a loop over chunks.
- Tests sit next to code: `chunker.py` has `test_chunker.py`. Write the test first.

## Stack

- Python 3.11+ with `uv`. FastAPI, pydantic v2. PyMuPDF for all PDF work.
- Index: `SqliteStore` (SQLite + rank_bm25 + numpy) behind `IndexStore`.
- AWS: Textract (stretch), Bedrock. Embeddings `amazon.titan-embed-text-v2:0` via boto3.
  Claude via the `anthropic` SDK's `AnthropicBedrockMantle(aws_region=...)`; model IDs in
  `.env`. Region in `.env`, default `ap-southeast-1`. Confirm model access in the console.
- `EMBED_FAKE=1` runs everything without AWS credentials (BM25 only).
- Web: Next.js (app router, latest from create-next-app), React 19, Tailwind 4, `pnpm`.

## Conventions

- Python: `ruff`, type hints, pydantic at package boundaries. Functions over classes.
- TypeScript: strict. Types in `web/lib/types.ts` mirror `contracts/` by hand.
- Commits: `<area>: <what>`, small and often.
- Branches: work on `dev-<name>`. Merge into `dev-law`, the integration branch. `main` is
  touched only at submission.
- Languages: `ms`, `en`, `mixed`. IDs: `doc_id` = sha256 of file bytes, first 16 hex.
  `chunk_id` = `{doc_id}:{page}:{n}`. Pages are 1-indexed.

## Commands

```
uv sync --extra dev
cp .env.example .env
uv run python -m engine.ingest samples/
uv run uvicorn api.main:app --reload
cd web && pnpm dev
uv run pytest
```
