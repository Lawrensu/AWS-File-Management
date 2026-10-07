# System design

This doc explains why Rujuk exists and how it works. Read it if you are a judge or a new teammate.

## Problem

- Agencies hold thousands of policies, SOPs, circulars, guidelines, reports and minutes.
- Finding the right one is slow.
- The brief: turn that pile into a searchable, intelligent resource.
- Staff should find answers faster and decide better.
- Sponsor is SDEC, Sarawak.
- Real documents are Malay and English, often mixed.

## What we score on

- Find faster.
  - Search understands meaning and works on scanned PDFs.
  - Demo: ask in plain language and get the right document and page in under 3 seconds.
- Decide better.
  - Answers, not links, with citations the user can verify.
  - Demo: "Can a contractor claim travel allowance?" returns a 3-line answer.
  - The answer cites the circular and page. The page opens with the passage highlighted.
- Context.
  - Bilingual retrieval makes a judge believe it would work in their office.

## Architecture

- Three pieces: the document store, the knowledge engine, and a thin web client.
- The document store is S3, standing in for the agency file share.
- Pitch line: point it at your existing file share, no migration.
- The knowledge engine is the ingest pipeline plus the index.
- The sections below cover ingest, index and search, query and answer, and the client.

## Ingest flow

- Runs once per document. Code in `engine/ingest/`.
- Extract text and blocks with PyMuPDF.
- Send scanned pages to Textract. This is a stretch goal.
- Chunk by page at 800 words with 100 overlap.
- Extract keywords with YAKE.
- Detect language with langdetect.
- Tag with Claude Haiku from a closed taxonomy. The same call finds what the document supersedes.
- Embed with Titan v2.
- Write to the index.
- Resolve supersession once after the whole folder is ingested.
- Ingest is idempotent on `doc_id`.

## Index and search

- Code in `engine/index/`. All access goes through the `IndexStore` interface.
- `SqliteStore` persists to SQLite. BM25 and a numpy vector matrix live in memory.
- BM25 weights rare terms higher, which gives the algorithmic common and rare word indexing.
- It uses the Lucene idf so a one-PDF index still gets keyword hits.
- Dense embeddings add cross-language matching.
- `hybrid_search` runs both rankings and fuses them with Reciprocal Rank Fusion.
- RRF uses k of 60 and a candidate pool of 200 per list.
- A department filter keeps that department or `Umum`.
- Superseded chunks are demoted by rank, not by score.
- `query_vec=None` means BM25 only.
- pgvector or OpenSearch can replace `SqliteStore` later without API changes.

## Query and answer flow

- Code in `api/`.
- Embed the question. If that fails, fall back to BM25 only.
- Run hybrid search with the viewer's department filter.
- `/search` returns result cards.
- `/ask` sends the top 8 chunks to Claude Sonnet on Bedrock.
- The prompt says: answer in the question's language, cite every claim, say not found otherwise.
- The answer streams over SSE. `[n]` markers map to citations.
- Page images are rendered server side with the cited passage highlighted.

## Client

- Code in `web/`. Next.js with React 19 and Tailwind 4.
- Search page with result cards, tags and a red Superseded badge.
- Ask page with a streamed answer and citation chips.
- Page viewer showing a server-rendered PNG with the passage highlighted.
- Department selector in the header. It is stored in localStorage and sent on every request.
- The client can run on mock JSON before the API exists.

## Data shapes

- Source of truth is `contracts/`. Read `contracts/README.md` first.
- `contracts/document.schema.json` is one document's metadata.
- `contracts/chunk.schema.json` is one indexed chunk.
- `contracts/taxonomy.json` holds the closed sets for doc_type, department, topic, status and lang.
- `contracts/api.md` lists every route with request and response.
- Key document fields: `doc_id`, `title`, `doc_type`, `department`, `status`, `superseded_by`, `supersedes`, `source_path`.
- Key chunk fields: `chunk_id`, `doc_id`, `page`, `bbox`, `heading`, `text`, `lang`, `source`, `embedding`.
- `doc_id` is the first 16 hex of the sha256 of the file bytes.
- `chunk_id` is `{doc_id}:{page}:{n}`, with n counting from 0 per page.
- Pages are 1-indexed. Every chunk has a page number.
- Languages are `ms`, `en` and `mixed`.
- Bboxes are `[x0, y0, x1, y1]` in PDF points, origin top-left.
- Errors are `{"error": "<message>"}`.

## Key decisions

- Four people, four hours. The order of work is in `docs/PLAN.md`.
- In-process SQLite, not pgvector. It saves an hour of setup.
- Python FastAPI, Next.js and PyMuPDF. One language per side, one PDF library.
- Closed tag taxonomy. Tags stay consistent and can drive filters.
- Tags run once per document on the cheapest capable model. Cost stays low.
- BM25 plus vectors with RRF. Keywords catch exact terms and vectors catch cross-language matches.
- Supersession is detected at ingest. The old document is badged and ranked lower.
- Tags and embeddings are cached by content hash. Re-ingest costs nothing.
- Answers are capped at 8 chunks. Cost and latency stay bounded.
- `EMBED_FAKE=1` runs everything without AWS. Teammates are never blocked on credentials.
- Department scoping is in the UI as Cognito-ready. Real access control is roadmap.
- Figures without text, such as flowcharts, are cut. They need a multimodal model.
- The name Rujuk is Malay for to refer or to consult.

## AWS services used

- Amazon Bedrock, Titan Text Embeddings v2, for embeddings.
- Amazon Bedrock, Claude Haiku, for tags and supersession.
- Amazon Bedrock, Claude Sonnet, for cited answers.
- Amazon Textract for scanned pages. Stretch goal.
- Amazon S3 as the document store. Optional for uploads through `S3_BUCKET`.
- Model IDs and region are set in `.env`. See `.env.example`.

## Roadmap

- Cognito access control.
- OpenSearch at scale.
- Figure description with a multimodal model.
- Conflict detection between live documents.
