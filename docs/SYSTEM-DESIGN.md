# System Design for Rujuk

This document describes the purpose, architecture and key decisions of Rujuk, document search and Q&A for government agencies.

Rujuk consists of:
- Backend: `engine/` (ingest and index) and `api/` (FastAPI), see [Backend Architecture](backend/BACKEND-ARCHITECTURE.md)
- Frontend: `web/` (Next.js client), see [Frontend Architecture](frontend/FRONTEND-ARCHITECTURE.md)

---

## Problem

- Agencies hold thousands of policies, SOPs, circulars, guidelines, reports and minutes.
- Finding the right one is slow.
- The brief: turn that pile into a searchable, intelligent resource.
- Staff should find answers faster and decide better.
- Real documents are Malay and English, often mixed, and some are scans.
- Sponsor is SDEC, Sarawak.

## Tool Stack

- Backend
	- Python 3.11+ with `uv`: one language for engine and API, fast installs
	- FastAPI (>=0.115) and pydantic v2 (>=2.8): typed routes and boundary models
	- PyMuPDF (>=1.24): one library for text, bboxes and page rendering
	- rank-bm25 and numpy: keyword and vector ranking in memory
	- SQLite: in-process storage, no server to set up
	- YAKE: keyword extraction without a model call
	- langdetect: language tag per chunk and per query
	- rapidfuzz: fuzzy title match for supersession
- AI
	- Amazon Bedrock, Cohere Embed Multilingual v3 in `ap-southeast-1`: embeddings, cross-language matching
	- Amazon Bedrock, Claude Haiku: tags and supersession, cheapest capable model
	- Amazon Bedrock, Claude Sonnet: cited answers
	- Groq free tier: fallback for tags and answers, `llama-3.1-8b-instant` and `llama-3.3-70b-versatile`
	- Amazon Textract: OCR for scanned pages, stretch goal
- Frontend
	- Next.js 16.4.0 app router: routes and server rendering
	- React 19.3.0: UI
	- Tailwind 4: styling
	- pnpm: package manager

## Repository Structure

```
contracts/   JSON schemas, taxonomy and API contract, source of truth for shared shapes
engine/
  ingest/    file to chunks with text, page, bbox, keywords, tags, embedding
  index/     IndexStore, SqliteStore, hybrid search, supersession
api/         FastAPI routes: /search, /ask, /documents
web/         Next.js client
samples/     synthetic seed corpus
eval/        retrieval questions and recall runner
scripts/     helper scripts, such as markdown to PDF
docs/        design, plan, demo and agent prompts
```

## System Functionality

- Staff
	- Search documents in Malay or English
		- Result cards with tags and a red Superseded badge
	- Ask a question and get a cited answer (planned)
		- Answer in the question's language
		- Every claim carries a `[n]` citation
		- Says not found when the documents do not answer
	- Open the cited page with the passage highlighted (planned)
	- Switch department view
		- Results keep that department plus `Umum`
		- Selection is sent on every request
- Document owner or admin
	- Upload a PDF (planned)
	- Run ingest on a folder (planned)
- System
	- Tag each document from a closed taxonomy (planned)
	- Detect language per chunk (planned)
	- Extract keywords (planned)
	- Detect supersession between documents
	- Demote superseded documents in ranking
	- OCR scanned pages with Textract (planned, stretch)

Notes:
- Real access control is not built. The department selector is Cognito-ready only.

## Application Layers

Cross sectional view of the application:

1. `web/` sends requests to the API with the viewer's department.
2. `api/` routes embed the question, call the index and shape the response.
3. `engine/index/` runs hybrid search behind the `IndexStore` interface.
4. `SqliteStore` holds documents and chunks in SQLite, with BM25 and vectors in memory.
5. `engine/ingest/` fills the store from PDFs.
6. AWS and Groq: Bedrock for embeddings, tags and answers, Textract for scans, Groq as the model fallback.

## Flow

### Ingest

1. Run `uv run python -m engine.ingest samples/` on a folder.
2. Extract text and blocks per page with PyMuPDF.
3. Send scanned pages to Textract (stretch).
4. Chunk by page, 800 words with 100 overlap.
5. Extract keywords with YAKE and detect language with langdetect.
6. Tag with Claude Haiku from the closed taxonomy. The same call lists what the document supersedes.
7. If Bedrock fails, tag with Groq. If that fails, use default tags. Ingest never fails on a tag.
8. Embed chunks with Cohere Embed Multilingual v3. With `EMBED_FAKE=1`, chunks get no real vectors and search runs on BM25 only.
9. Write the document and chunks to the store. Ingest is idempotent on `doc_id`.
10. After the whole folder, run supersession once.

### Query and Answer

1. Staff send a question with their department.
2. The API embeds the question. If that fails, it passes no vector and search runs on BM25 only.
3. `hybrid_search` runs BM25 and vector rankings and fuses them with Reciprocal Rank Fusion.
4. The department filter keeps that department or `Umum`.
5. Superseded chunks are demoted by rank and still returned.
6. `/search` returns result cards.
7. `/ask` sends the top 8 chunks to Claude Sonnet on Bedrock.
8. If Bedrock fails, `/ask` falls back to Groq with the top 5 chunks.
9. The answer streams over SSE. `[n]` markers map to citations.
10. The viewer opens the cited page as a PNG with the passage highlighted.

## Key Decisions

- Four people, four hours. The order of work is in [PLAN](PLAN.md).
- In-process SQLite, not pgvector: saves an hour of setup. pgvector or OpenSearch can replace it behind `IndexStore`.
- FastAPI, Next.js and PyMuPDF: one language per side, one PDF library.
- Closed tag taxonomy: tags stay consistent and can drive filters.
- Tags run once per document on the cheapest capable model: cost stays low.
- BM25 plus vectors with RRF: keywords catch exact terms, vectors catch cross-language matches.
- Cohere Embed Multilingual v3 for embeddings: Titan v2 is not offered in `ap-southeast-1`, and staying in that region keeps data close to Sarawak. It is multilingual and has the same 1024 dimensions, so the contracts and the index do not change.
- Claude model IDs are pending a retest after AWS account verification.
- Supersession is detected at ingest: the old document is badged and ranked lower, not removed.
- Tags and embeddings are cached by content hash: re-ingest costs nothing.
- Answers are capped at 8 chunks: cost and latency stay bounded.
- No paid services: Bedrock runs on a $100 AWS credit with a $1 budget alert.
- AWS credentials live on Lawrence's machine only: the integrated demo runs there.
- Teammates develop with `EMBED_FAKE=1` and mocks: nobody is blocked on credentials.
- Groq free tier is the fallback for tags and answers: it needs no credit card.
- No embedding fallback: without Bedrock, search runs on BM25 only.
- One shared `engine/llm.py` will hold the Bedrock call and the Groq fallback, added after A4 and C3.
- Department scoping is in the UI as Cognito-ready: real access control is roadmap.
- Figures without text, such as flowcharts, are cut: they need a multimodal model.
- The name Rujuk is Malay for to refer or to consult.

---

# TODO (future)

- Cognito access control.
- OpenSearch at scale.
- Figure description with a multimodal model.
- Conflict detection between live documents.

# Open Questions

- Items marked "(planned)" wait on ingest and the API. Remove each marker as its task lands.
- Uploads go to `data/uploads/`. Writing them to S3 through `S3_BUCKET` is optional and not built.
- Contract and prompt mismatches found during review are listed in [Backend Architecture](backend/BACKEND-ARCHITECTURE.md), under Open Questions.
