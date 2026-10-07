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
- `engine/llm.py` The one LLM entry point: `complete`, `stream`, `preferred_provider`. Bedrock first, then Groq.
- `engine/testing.py` `FakeStore` and fixtures. Every test uses these, never `SqliteStore`.
- `api/` C. FastAPI with `/search`, `/ask`, `/documents`.
- `web/` D. Next.js client.
- `samples/` synthetic seed corpus. `eval/` retrieval questions and runner.
- `docs/` system design, getting started, plan, agent prompts, demo script. `docs/backend/` and `docs/frontend/` hold the detailed architecture docs.

## Rules

- Contracts first. A new field goes into `contracts/` in its own commit, and you tell the team.
- No undocumented fields in API responses.
- Stay in your package.
- Need something from another package? Call its interface and leave a `TODO(<letter>)`.
- Every chunk has a page number. No exceptions.
- No real government documents in the repo.
- No secrets in code. `.env` is gitignored, `.env.example` is committed.
- Every LLM call goes through `engine/llm.py` (`complete` or `stream`). Never import `anthropic` or `groq`, or call a Claude or Llama endpoint, anywhere else.
- Bedrock calls are cached or batched. Never call a model inside a loop over chunks.
- Tests sit next to code. `chunker.py` has `test_chunker.py`. Write the test first.

## Stack

- Python 3.11+ with `uv`. FastAPI, pydantic v2. PyMuPDF for all PDF work.
- Index: `SqliteStore` on SQLite, rank_bm25 and numpy, behind `IndexStore`.
- AWS: Textract as a stretch, and Bedrock.
- Embeddings: Cohere Embed Multilingual v3 (`cohere.embed-multilingual-v3`, 1024 dims) on Bedrock in `ap-southeast-1`, via boto3. Titan v2 is not offered there. Documents embed as `search_document`; API code embeds questions with `input_type="query"`.
- Claude: only through `engine/llm.py`. `.env` sets `BEDROCK_CLIENT=converse`, boto3 Converse with global inference profile IDs. The Mantle client returned 404 for every Claude model on this account. Model IDs are in `.env`.
- Bedrock Claude is blocked until AWS approves the Anthropic use case form, so Groq serves today. When Bedrock starts working it takes over with no code change.
- Region is in `.env`. The default is `ap-southeast-1`. Confirm model access in the console.
- Fallback: Groq free tier for tagging and answers when Bedrock fails, via `GROQ_API_KEY`, inside `engine/llm.py`. No embedding fallback; search drops to BM25 only.
- No paid services. Bedrock runs on a $100 credit with a $1 budget alert.
- Only Lawrence's machine has model access, AWS and Groq. Everyone else sets `EMBED_FAKE=1`, leaves `GROQ_API_KEY` empty, and stubs `engine.llm` and `embed_texts` in tests.
- On a machine without keys, `engine.llm` raises `LLMUnavailable`. That is expected. Do not debug provider, credential or network errors there, and test the `LLMUnavailable` path with a stub.
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

- Applies to `README.md`, `AGENTS.md`, and everything in `docs/`.
- Top-level docs are short and link out. Detail goes in `docs/backend/` and `docs/frontend/`.
- The title is an H1, followed by one purpose sentence and, for long docs, a bullet list of what the doc covers and links to related docs.
- Long docs split into parts with a line containing only `---`. Each part is an H1: Overview, Implementation Details, TODO (future), Open Questions. Use H2 and H3 inside parts.
- Point form. Numbered lists only for ordered steps.
- No markdown tables. No em dashes.
- Directory trees and routes go in code blocks. Commands go in fenced bash blocks. Paths go in backticks.
- File names in `docs/` are UPPER-KEBAB.md.
