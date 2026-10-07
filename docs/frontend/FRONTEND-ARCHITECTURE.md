# Frontend Architecture

Document search and question answering UI for government agencies. This document describes the Next.js app structure, API client, component organization, and how the frontend integrates with the backend via the contract in `contracts/api.md`.

- [System Design](../SYSTEM-DESIGN.md)
- [Backend Architecture](../backend/BACKEND-ARCHITECTURE.md)
- [API contract](../../contracts/api.md)

---

# Overview

## Frontend Repo Structure

```
web/app/
	layout.tsx			Root layout with fonts and metadata.
	page.tsx			Search page, query and results.
	ask/page.tsx			Ask page, question and streamed answer.
	doc/[id]/page.tsx		Document viewer, page navigation and highlight.
web/components/
	Header.tsx			Logo, nav links, department selector.
	SearchBar.tsx			Query input and search button.
	ResultCard.tsx			Search result card with snippet and metadata.
	DepartmentSelect.tsx		Department dropdown with localStorage persistence.
web/lib/
	types.ts			Mirror of contracts/api.md and document schemas.
	api.ts				HTTP client, BASE_URL config, mock mode toggle.
	citations.ts			Parse answer text, map [n] markers to citations.
	taxonomy.ts			Constants: departments and document types.
web/mock/
	search.json			Mock search results.
	documents.json			Mock documents with chunks.
web/public/mock/
	page.svg			Mock page image.
```

## Layers

- Pages call `lib/api.ts` only. Never call the backend directly.
- `lib/types.ts` mirrors `contracts/` by hand and must stay in sync.
- Components are presentational. State lives in pages. No API calls from components.

---

# Implementation Details

## Pages

### Search /

Shows search query box, department selector, and result cards that link to the viewer.

API calls:
- `health()` on mount to check API and show document count.
- `search(req)` when user submits a query, with department filter.

Query params: none.

States:
- Idle: initial, waiting for query.
- Loading: search in progress.
- Error: HTTP error or network failure.
- Done: results rendered, empty results shown as "No results found / Tiada keputusan."

### Ask /ask

Shows question textarea, shows streamed answer with citation chips and sources list.

API calls:
- `ask(req)` with question and department filter, `stream: false` (streaming not yet implemented).

Query params: none.

States:
- Idle: initial, waiting for question.
- Loading: answer in progress.
- Error: HTTP error or network failure.
- Done: answer rendered, with citations mapped to source links. "Not found" answers shown as plain text.

### Viewer /doc/[id]

Shows page PNG from the backend, with prev and next buttons. Query param `page` sets the page number (default 1). Query param `highlight=chunk_id` draws a yellow rectangle on the chunk.

API calls:
- `document(id)` to fetch document metadata and chunks.
- `pageImageUrl(docId, page, highlightChunkId)` to build the PNG URL (no HTTP call, just URL construction).

Query params:
- `page=N`: page number to show.
- `highlight=chunk_id`: chunk to highlight (optional).

States:
- Loading: document metadata fetching.
- Error: document not found (404) or network failure.
- Done: page rendered with prev/next buttons, disabled when at boundaries.

## Components

- Header: renders logo, nav links to search and ask, and department selector. Receives department value and onChange callback.
- SearchBar: query input with bilingual placeholder. onSubmit callback fires on form submit. Disabled prop disables the button.
- ResultCard: links to viewer, shows title, snippet, doc_type tag, department tag, red Superseded badge if status is "superseded".
- DepartmentSelect: dropdown that calls onChange. Exposes useDepartment hook for reading/writing to localStorage.

## API Client

`lib/api.ts` exports:

- `BASE_URL`: from `NEXT_PUBLIC_API_URL` env var or default "http://localhost:8000".
- `USE_MOCK`: true if `NEXT_PUBLIC_USE_MOCK=1`.
- `ApiError`: error class with status code. Thrown by all request functions.
- `health()`: Promise<HealthResponse>. Mock returns {ok: true, documents: 3, chunks: 6}.
- `search(req)`: Promise<SearchResponse>. Mock returns search.json.
- `ask(req)`: Promise<AskResponse>. Mock returns a Malay answer about contractor travel allowance. Hardcoded `stream: false` in the request, actual streaming not implemented.
- `documents()`: Promise<Document[]>. Mock returns all documents (minus chunks).
- `document(id)`: Promise<DocumentDetail>. Mock looks up by id, rejects 404 if not found.
- `pageImageUrl(docId, page, highlightChunkId)`: string. Returns the URL for `/documents/{docId}/pages/{page}.png?highlight=chunk_id`. Mock returns "/mock/page.svg".

## Citations

`lib/citations.ts` exports:

- `AnswerSegment`: discriminated union of text and cite segments.
- `citationHref(citation)`: string. Builds `/doc/{doc_id}?page={page}&highlight={chunk_id}` for linking to the viewer.
- `parseAnswer(answer, citations)`: AnswerSegment[]. Splits the answer string on `[n]` markers and maps them to Citation objects. Markers with no matching citation stay in the text. Pure function, works on partial strings while streaming.

## Mock Mode

When `NEXT_PUBLIC_USE_MOCK=1`:
- All API calls return hardcoded responses without hitting the backend.
- `health()` returns 3 documents and 6 chunks.
- `search()` returns search.json with 3 results (one current, one superseded).
- `ask()` returns a Malay answer about contractor travel allowance with one citation.
- `documents()` returns the three documents in documents.json (chunks omitted).
- `document(id)` returns the full document from documents.json or rejects 404.
- `pageImageUrl()` returns "/mock/page.svg" (a placeholder SVG).

Mock data files:
- `web/mock/search.json`: SearchResponse with 3 results.
- `web/mock/documents.json`: object keyed by doc_id, values are DocumentDetail.
- `web/public/mock/page.svg`: placeholder page image.

## Department Scoping

`useDepartment()` hook in DepartmentSelect.tsx:

- Reads `rujuk.department` from localStorage on mount.
- Validates against DEPARTMENTS taxonomy. Defaults to "Umum" if invalid or missing.
- All search and ask calls pass `filters: { department }`.
- The backend keeps documents of that department plus documents tagged "Umum".
- Selecting "Umum" means no department filter.
- On the search page, changing the department re-runs the current search.

## Configuration

Environment variables:

- `NEXT_PUBLIC_API_URL`: Backend URL. Defaults to "http://localhost:8000". Read by api.ts.
- `NEXT_PUBLIC_USE_MOCK`: Set to "1" to use mock mode. Defaults to "0" (real API).

Set these in `.env.local` or `.env.local.example` (the latter is committed).

---

# TODO (future)

- Streaming answers over SSE (planned). The ask page sends `stream: false` today. Once `POST /ask` streams, render tokens as they arrive and re-run `parseAnswer` on the partial text.
- Upload page (planned). Depends on `POST /documents/upload`, which is not built yet.

---

# Open Questions

- Should the ask page re-run the last question when the department changes, as the search page does?
