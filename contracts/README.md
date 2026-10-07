# Contracts

Source of truth for every shape that crosses a package boundary. Python mirrors these in
`api/models.py`. TypeScript mirrors them in `web/lib/types.ts`. Change a file here first, in
its own commit, and tell the team.

- `taxonomy.json`: closed sets for doc_type, department, topic, status, lang. Used by the
  tagger (A4) and the UI filters (D2, D6).
- `document.schema.json`: one document's metadata. Used by A6, B1, C4, D2.
- `chunk.schema.json`: one indexed chunk. Used by A2, B1, B2.
- `api.md`: every route, request and response. Used by all of C and D.

Conventions: `doc_id` is the first 16 hex of sha256(file bytes). `chunk_id` is
`{doc_id}:{page}:{n}`, n from 0 per page. Pages are 1-indexed. Languages are `ms`, `en`,
`mixed`. Bboxes are `[x0, y0, x1, y1]` in PDF points, origin top-left (PyMuPDF).
