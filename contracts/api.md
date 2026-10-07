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
