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

- `503 {"error": "index not ready"}` — returned by `POST /search` and `POST /ask`
  when `app.state.store is None` (e.g. `SqliteStore` not implemented yet or `INDEX_PATH`
  missing). `GET /health` never 503s; it returns `{"ok": true, "documents": 0, "chunks": 0}`
  in that state.
- `400 {"error": "<reason>"}` — `POST /documents/upload` when the file is not `.pdf`,
  when the multipart field is not named `file`, or when the file is empty.
- `404 {"error": "<reason>"}` — `GET /documents/{doc_id}` for unknown `doc_id`;
  `GET /documents/{doc_id}/pages/{page}.png` for unknown `doc_id` or page out of range
  (`page < 1` or `page > page_count`). A `highlight` chunk with zero `search_for` hits
  does NOT 404 — it returns the plain PNG (highlight is best-effort).
- Bedrock failures (`POST /ask` answer generation, query embedding) surface as
  `503 {"error": "answer model unavailable: <model_id> in <region>"}` or
  `503 {"error": "embedding unavailable: <detail>"}`. They never take down the app;
  `POST /search` without embedding and `GET /documents` keep working when possible.

### Filtering (search and ask)
`filters` fields are all optional. Defaults: `department: null, doc_type: null,
include_superseded: false`.

- `department: null` or `"Umum"` means no department filter. Otherwise exact match
  against `Document.department` (one of `taxonomy.json: department`).
- `doc_type: null` means no type filter. Otherwise exact match against
  `taxonomy.json: doc_type`.
- `include_superseded: false` (default) does NOT remove superseded docs — matching
  chunks from docs with `status == "superseded"` get `score * 0.3` so the UI can still
  show the red "Superseded" badge. `true` restores full score. See B2 RRF spec.
- `top_k`: default 10, max 50. `POST /ask` always uses top 8 chunks for the prompt
  regardless of `top_k` (retrieval `k=8` internally).

### Streaming (POST /ask with `"stream": true`)
- Request: same as non-streaming plus `"stream": true`.
- Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`.
- Event 1..N: `data: {"type": "token", "text": "..."}` — raw model token deltas, in order.
- Final event: `data: {"type": "done", "answer": {...full non-streaming AskResponse...}}`
  where `AskResponse` is `{answer, language, confidence, citations[], not_found}` per
  the `POST /ask` section above. Clients must parse only the `done` event for citations.
- `[n]` markers in `answer` map 1:1 to `citations[].n` in order of first appearance.
  `n` is 1-indexed into the top-8 excerpt list for that request.

### Viewer (GET page PNG)
- Renders with PyMuPDF at ~110 dpi. Response: `image/png` with
  `Cache-Control: public, max-age=3600`.
- `?highlight=<chunk_id>`: server takes the first 120 chars of chunk text, calls
  `page.search_for(text)`; on zero hits retries with first 60 chars. Each hit rect is
  drawn yellow (`fill=(1, 0.85, 0), fill_opacity=0.35`) before rendering. Zero hits
  after retry returns the unhighlighted page (still 200).
