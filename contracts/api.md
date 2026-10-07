# API contract

Base URL from `NEXT_PUBLIC_API_URL`. All JSON. All errors are `{"error": "<message>"}` with
a 4xx or 5xx status. CORS is open for the hackathon.

## GET /health
`200 {"ok": true, "documents": 15, "chunks": 212}`

## POST /search
Request
```json
{
  "query": "elaun perjalanan kontraktor",
  "filters": {
    "department": "Jabatan Kewangan",
    "doc_type": null,
    "include_superseded": false
  },
  "top_k": 10
}
```
All filter fields optional. `department` is the viewer's department from the UI selector;
`null` or `"Umum"` means no department filter.

Response
```json
{
  "results": [
    {
      "chunk_id": "a1b2c3d4e5f60718:4:1",
      "doc_id": "a1b2c3d4e5f60718",
      "title": "Pekeliling Perbendaharaan Bil. 3/2024",
      "page": 4,
      "snippet": "...kadar elaun perjalanan bagi kontraktor adalah...",
      "score": 0.0312,
      "doc_type": "circular",
      "department": "Jabatan Kewangan",
      "status": "current",
      "superseded_by": null,
      "lang": "ms"
    }
  ]
}
```
`snippet` is the chunk text trimmed to about 300 characters around the best match (or just
the first 300 characters). `score` is the RRF score, only meaningful for ordering.

## POST /ask
Request: same shape as `/search` but the field is `question`, plus optional `stream: true`.

Non-streaming response
```json
{
  "answer": "Ya, kontraktor layak menuntut elaun perjalanan pada kadar RM0.70/km [1]. Tuntutan mesti disokong oleh log perjalanan [2].",
  "language": "ms",
  "confidence": "high",
  "citations": [
    {
      "n": 1,
      "chunk_id": "a1b2c3d4e5f60718:4:1",
      "doc_id": "a1b2c3d4e5f60718",
      "title": "Pekeliling Perbendaharaan Bil. 3/2024",
      "page": 4,
      "status": "current",
      "quote": "kadar elaun perjalanan bagi kontraktor adalah RM0.70 bagi setiap kilometer"
    }
  ],
  "not_found": false
}
```
`confidence` is one of `high`, `medium`, `low`. `high` when the top RRF score is at or above a
threshold C3 tunes on real data, `medium` below it, `low` when the model answered "not found".
BM25-only scores are about half of hybrid scores, so the threshold must account for that. `not_found: true` means the answer is the standard not-found sentence.
`[n]` markers in `answer` map to `citations[].n`.

Streaming (`stream: true`): `text/event-stream`. Events:
- `data: {"type": "token", "text": "..."}` repeated
- `data: {"type": "done", "answer": {...full non-streaming response...}}`

## GET /documents
`200 {"documents": [Document, ...]}` (schema in `document.schema.json`, no chunks).

## GET /documents/{doc_id}
`200 Document` plus `"chunks": [Chunk without embedding, ...]`.

## GET /documents/{doc_id}/pages/{page}.png?highlight={chunk_id}
PNG of the page at about 110 dpi. If `highlight` is given, the chunk's passage is drawn with
a translucent yellow rectangle before rendering. 404 if page out of range.

## POST /documents/upload
Multipart form, field `file`. Ingests synchronously.
`200 {"doc_id": "...", "title": "...", "pages": 6, "chunks": 14, "status": "current", "department": "..."}`

## Notes for Workstream C implementation (clarifications, no new fields)

### Errors
All errors are `{"error": "<message>"}` with a 4xx/5xx status (see top of file).
Workstream C uses:

- `503 {"error": "index not ready"}`: any route that needs the store, when
  `app.state.store is None`. The lifespan falls back to an empty `FakeStore` if
  `SqliteStore(INDEX_PATH)` fails, so in practice this only shows up in tests.
  `GET /health` never 503s; it returns `{"ok": true, "documents": 0, "chunks": 0}`.
- `400 {"error": "<reason>"}`: `POST /documents/upload` when the multipart field `file` is
  missing, the name does not end in `.pdf`, the bytes do not start with `%PDF`, the file is
  empty, or it is over 50 MB.
- `404 {"error": "<reason>"}`: `GET /documents/{doc_id}` for an unknown `doc_id`;
  `GET /documents/{doc_id}/pages/{page}.png` for an unknown `doc_id`, a page out of range
  (`page < 1` or `page > page_count`), or a source PDF that is not on disk. A `highlight`
  with zero `search_for` hits does not 404; it returns the plain PNG.
- `422 {"error": "<field>: <reason>"}`: request body fails validation (for example
  `top_k` over 50 or an empty `query`).
- `503 {"error": "answer model unavailable: <detail>"}`: `POST /ask` when `engine.llm`
  raises `LLMUnavailable` (no provider available, or every provider failed before the
  first token).
- Query embedding failure never returns an error. `/search` and `/ask` drop to BM25 only.
- A provider failure after the first token ends the answer early; the stream still ends
  with a `done` event.

### Filtering (search and ask)
`filters` fields are all optional. Defaults: `department: null, doc_type: null,
include_superseded: false`.

- `department: null` or `"Umum"` means no department filter. Otherwise exact match
  against `Document.department` (one of `taxonomy.json: department`).
- `doc_type: null` means no type filter. Otherwise exact match against
  `taxonomy.json: doc_type`.
- `include_superseded: false` (default) does not remove superseded docs. Their chunks are
  ranked as if they sat 5 places lower in every list (`SUPERSEDED_RANK_OFFSET` in B2), so
  they stay visible below the current document and the UI can show the red badge.
  `true` turns the demotion off.
- `top_k`: default 10, max 50. `POST /ask` ignores it and uses the top 8 chunks when
  `engine.llm.preferred_provider("answer")` is `bedrock`, or the top 5 when it is `groq`.
- `POST /ask` with no matching chunks returns the not-found answer without calling a model.

### Streaming (POST /ask with `"stream": true`)
- Request: same as non-streaming plus `"stream": true`.
- Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`.
- Event 1..N: `data: {"type": "token", "text": "..."}`, raw model text deltas in order.
- Final event: `data: {"type": "done", "answer": {...full non-streaming AskResponse...}}`
  where `AskResponse` is `{answer, language, confidence, citations[], not_found}` per
  the `POST /ask` section above. Clients must parse only the `done` event for citations.
- `[n]` markers in `answer` map to `citations[].n` in order of first appearance. `n` is
  1-indexed into the excerpt list for that request (8 or 5 long). Out-of-range markers are
  dropped from `citations` but left in the text.
- `LLMUnavailable` is raised before streaming starts, so it is a plain JSON 503, not SSE.
- Headers `X-Rujuk-Provider` and `X-Rujuk-Model` (exposed via CORS) name the provider and
  model that actually answered. They are headers, not body fields.

### Viewer (GET page PNG)
- Renders with PyMuPDF at ~110 dpi. Response: `image/png` with
  `Cache-Control: public, max-age=3600`.
- `?highlight=<chunk_id>`: server takes the first 120 chars of chunk text, calls
  `page.search_for(text)`; on zero hits retries with first 60 chars. Each hit rect is
  drawn yellow (`fill=(1, 0.85, 0), fill_opacity=0.35`) before rendering. Zero hits
  after retry returns the unhighlighted page (still 200). A chunk from another document
  or page is ignored.
