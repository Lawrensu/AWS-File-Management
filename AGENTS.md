# AGENTS.md

Rules for every coding agent and every human on this repo. `CLAUDE.md` and
`.kiro/steering/project.md` point here.

## What we are building

- Rujuk: document search and question answering for government agencies.
- Documents are ingested, OCR'd if scanned, tagged, and indexed with hybrid BM25 + vector search.
- A chat UI returns cited answers with page highlights.
- Bilingual Malay and English.
- Why and how: `docs/SYSTEM-DESIGN.md`.
- Who does what: `docs/PLAN.md`.
- How to run it: `docs/GETTING-STARTED.md`.

## Layout

- `contracts/` JSON schemas and the API contract. Source of truth for every shared shape.
- `engine/ingest/` A. File to chunks with text, page, bbox, keywords, tags, embedding.
- `engine/index/` B. `IndexStore` interface, `SqliteStore`, hybrid search, supersession.
- `engine/testing.py` `FakeStore` and fixtures. Every test uses these, never `SqliteStore`.
- `api/` C. FastAPI with `/search`, `/ask`, `/documents`.
- `web/` D. Next.js client.
- `samples/` synthetic seed corpus. `eval/` retrieval questions and runner.
- `docs/` system design, getting started, plan, agent prompts, demo script.

## Rules

- Contracts first. A new field goes into `contracts/` in its own commit, and you tell the team.
- No undocumented fields in API responses.
- Stay in your package.
- Need something from another package? Call its interface and leave a `TODO(<letter>)`.
- Every chunk has a page number. No exceptions.
- No real government documents in the repo.
- No secrets in code. `.env` is gitignored, `.env.example` is committed.
- Bedrock calls are cached or batched. Never call a model inside a loop over chunks.
- Tests sit next to code. `chunker.py` has `test_chunker.py`. Write the test first.

## Stack

- Python 3.11+ with `uv`. FastAPI, pydantic v2. PyMuPDF for all PDF work.
- Index: `SqliteStore` on SQLite, rank_bm25 and numpy, behind `IndexStore`.
- AWS: Textract as a stretch, and Bedrock.
- Embeddings: `amazon.titan-embed-text-v2:0` via boto3.
- Claude: the `anthropic` SDK's `AnthropicBedrockMantle(aws_region=...)`. Model IDs are in `.env`.
- Region is in `.env`. The default is `ap-southeast-1`. Confirm model access in the console.
- Fallback: Groq free tier for tagging and answers when Bedrock fails, via `GROQ_API_KEY`. No embedding fallback; search drops to BM25 only.
- No paid services. Bedrock runs on a $100 credit with a $1 budget alert.
- AWS credentials exist only on Lawrence's machine. Elsewhere, set `EMBED_FAKE=1` and mock Bedrock in tests.
- Read every model ID and the region from `.env`. Never hardcode them.
- A Bedrock failure must never crash ingest or the API. Catch it and fall back.
- `EMBED_FAKE=1` runs everything without AWS credentials, on BM25 only.
- Web: Next.js app router, React 19, Tailwind 4, `pnpm`.

## Conventions

- Python: `ruff`, type hints, pydantic at package boundaries. Functions over classes.
- TypeScript: strict. Types in `web/lib/types.ts` mirror `contracts/` by hand.
- Commits: `<area>: <what>`, small and often.
- Branches: work on `dev-<name>`. Merge into `dev-law`, the integration branch.
- `main` is touched only at submission.
- Languages are `ms`, `en`, `mixed`.
- `doc_id` is the sha256 of the file bytes, first 16 hex.
- `chunk_id` is `{doc_id}:{page}:{n}`. Pages are 1-indexed.

## Commands

```bash
uv sync --extra dev
cp .env.example .env
uv run python -m engine.ingest samples/
uv run uvicorn api.main:app --reload
cd web && pnpm dev
uv run pytest
```

## Docs convention

- Applies to `README.md`, `AGENTS.md`, and every file in `docs/`.
- Point form. No markdown tables.
- One H1 as the title, then H2 sections only. No H3 or deeper.
- First line under the title: one sentence on what the doc is for and who should read it.
- Short sentences. One idea per bullet.
- No em dashes. No parentheses.
- Commands and paths go in backticks. Multi-line commands go in fenced bash blocks.
- File names in `docs/` are UPPER-KEBAB.md.
