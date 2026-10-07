# Brainstorm

Problem from the brief: agencies hold thousands of policies, SOPs, circulars, guidelines,
reports and minutes. Finding the right one is slow. Turn that pile into a searchable,
intelligent resource so staff find answers faster and decide better.

## What the judges score

- Find faster: search that understands meaning, works on scanned PDFs. Demo: ask in plain
  language, get the right document and page in under 3 seconds.
- Decide better: answers, not links, with citations the user can verify. Demo: "Can a
  contractor claim travel allowance?" returns a 3-line answer citing the circular and page,
  and the page opens with the passage highlighted.
- Context: sponsor is SDEC, Sarawak. Real documents are Malay and English, often mixed.
  Bilingual retrieval is what makes a judge believe it would work in their office.

## Our initial ideas, sharpened

- Central vs client system. Keep it, as three pieces: the document store (S3, playing the
  agency's file share), the knowledge engine (ingest pipeline plus index), and a thin web
  client. Pitch line: point it at your existing file share, no migration.
- Vision and OCR. Scanned text pages go to Amazon Textract. Figures with no text, such as
  flowcharts, would need a multimodal model to describe them; cut for the 4-hour build,
  roadmap item.
- Algorithmic indexing on common and rare words. That is BM25, which already weights rare
  terms higher. Use it, add YAKE keyword extraction for metadata, add dense embeddings for
  cross-language matching, and fuse the two rankings with Reciprocal Rank Fusion.
- LLM tags. Yes, but from a closed taxonomy so tags stay consistent and can drive filters.
  Run once per document at ingest with the cheapest capable model.

## Differentiators we ship

- Cited answers with page highlight.
- Bilingual: ask in one language, retrieve from the other.
- Supersession awareness: detect "this circular replaces X", badge the old one, prefer the
  new one.
- Department scoping in the UI, presented as Cognito-ready. Real access control is roadmap.

## Architecture

- Ingest, once per document: PyMuPDF text and blocks, Textract for scanned pages, chunk by
  page at 800 words, YAKE keywords, langdetect, Claude Haiku tags and supersedes, Titan v2
  embeddings, write to the index, resolve supersession.
- Index: SQLite for persistence, BM25 and a numpy vector matrix in memory, behind the
  `IndexStore` interface. pgvector or OpenSearch can replace it later without API changes.
- Query: embed the question, BM25 and vector search in parallel, RRF merge, department
  filter, superseded demotion. `/search` returns cards. `/ask` sends the top 8 chunks to
  Claude with "answer in the question's language, cite every claim, say not found
  otherwise", streams the answer, maps `[n]` to chunks.
- Client: Next.js. Search page, ask page with citation chips, page viewer showing a
  server-rendered PNG with the passage highlighted.
- Cost: tags and embeddings computed once and cached by content hash. Answers capped at 8
  chunks. `EMBED_FAKE=1` for development without AWS.

## Decisions

- Team of 4, 4 hours. Order of work in `docs/PLAN.md`.
- Index store in-process SQLite, not pgvector, to save an hour of setup.
- Stack: Python FastAPI, Next.js, PyMuPDF.
- Name: Rujuk (Malay: to refer, to consult).
- Roadmap for the last slide: Cognito access control, OpenSearch at scale, figure
  description, conflict detection between live documents.
