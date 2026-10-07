# Contracts

Source of truth for every data shape that crosses a package boundary. Python code mirrors
these in `api/models.py` (pydantic). TypeScript mirrors them in `web/lib/types.ts`.

Change a schema here first, in its own commit, and tell the team.

| File | Used by |
|---|---|
| `taxonomy.json` | A4 tagger (closed sets), D2/D6 UI filters |
| `document.schema.json` | A6, B1, C4, D2 |
| `chunk.schema.json` | A2, B1, B2 |
| `api.md` | C1 to C5, D1 to D6 |

Conventions: `doc_id` = first 16 hex of sha256(file bytes). `chunk_id` = `{doc_id}:{page}:{n}`
with `n` starting at 0. Pages are 1-indexed. Languages are `ms` or `en`. Bboxes are in PDF
points relative to the page, `[x0, y0, x1, y1]`, origin top-left (PyMuPDF convention).
