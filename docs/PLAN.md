# 4-Hour Delegation Plan

Confirmed: 4 people, all four differentiators, 4 hours. That is tight, so this plan is built
so the demo works at every checkpoint. If the clock runs out, whatever is done at the last
checkpoint is what we show.

Index store: pgvector was chosen, but Docker + Postgres + migrations costs about an hour of
one person's four. Start with an in-process SQLite + numpy store behind the same `IndexStore`
interface (40 minutes). Swap to pgvector only as a stretch (B5). Same API, same demo.

Access control: Cognito is not a 4-hour item. Ship "department scoping": every document has a
department tag, the UI has a department selector, search filters by it. Say "Cognito-ready" in
the pitch. That is honest and takes 10 minutes.

Legend: **[A]** hand to a small agent (Haiku, DeepSeek, Kiro autopilot) with the task row and
`AGENTS.md`, review the diff. **[H]** the human does it. Times are targets, not estimates.

---

## Timeline

| Clock | Checkpoint | Must be true |
|---|---|---|
| 0:00 | Kickoff | Everyone has read `AGENTS.md` and `contracts/`. `uv sync` works. `aws sts get-caller-identity` works. Bedrock model access confirmed in the console for the region. |
| 0:15 | Start | Agents launched on every [A] task that has no dependency. Seed corpus generation (D4) started, it runs in the background the whole time. |
| 1:30 | **Vertical slice** | One native PDF ingested, `/ask` returns a cited answer, UI shows it. Nothing else matters until this is true. |
| 3:00 | **Feature freeze** | Bilingual, supersession, highlight, department filter working on the seed corpus. Textract if it landed. |
| 3:30 | Demo locked | Three questions rehearsed twice. Backup screen recording made. |
| 4:00 | Submit | Deck done, repo pushed, URL or video ready. |

---

## Workstream A: Ingest  (Malissa)

Package `engine/ingest/`. Uses PyMuPDF for all PDF work (text, blocks, bboxes, page render).

| # | Task | Mode | Mins | Done when |
|---|---|---|---|---|
| A1 | `extract_pages(path) -> list[Page]` with PyMuPDF: text per page, text blocks with bbox, `is_scanned` flag when a page has under 50 chars of text | [A] | 15 | test on a native PDF returns pages with text and bboxes |
| A2 | `chunk_pages(pages) -> list[Chunk]`: per page, split at 800 tokens / 100 overlap (tiktoken cl100k or simple whitespace count), keep page and the bbox of the first block | [A] | 20 | tests: short page = 1 chunk, long page = n chunks, every chunk has page >= 1 |
| A3 | `embed_texts(list[str]) -> np.ndarray` via Bedrock Titan Text Embeddings v2 (`amazon.titan-embed-text-v2:0`, 1024 dims, boto3 `bedrock-runtime` invoke_model), batched, cached in `~/.cache/rujuk/embed.sqlite` by sha256 | [H] | 20 | second call on the same text makes zero API calls (assert via mock) |
| A4 | `tag_document(title, first_3_pages_text) -> DocMeta` via Claude on Bedrock. Returns strict JSON matching `contracts/document.schema.json` fields `doc_type, department, topics, year, lang, supersedes`. Prompt in `engine/ingest/prompts/tagger.md`. Use the taxonomy in `contracts/taxonomy.json`, tell the model to pick only from it | [H] | 30 | 5 seed docs tagged correctly by eye, invalid JSON retried once then falls back to `unknown` |
| A5 | `extract_keywords(text, lang) -> list[str]` with YAKE top 10; `detect_lang(text) -> "ms"\|"en"` with langdetect | [A] | 15 | Malay and English samples give sensible keywords and the right lang |
| A6 | `ingest_file(path, store) -> IngestResult`: A1 -> A2 -> A5 -> A4 -> A3 -> `store.upsert`. Idempotent on `doc_id = sha256(bytes)[:16]`. CLI: `uv run python -m engine.ingest samples/` | [H] | 20 | runs over `samples/` and prints doc count and chunk count |
| A7 | **Stretch, time-box 30 min, start only after 1:30.** Textract `detect_document_text` for pages where `is_scanned`. Replace page text and blocks with Textract lines + bboxes | [H] | 30 | one scanned seed doc becomes searchable. If not working by 2:15, stop and demo native PDFs only |

## Workstream B: Index and retrieval  (Noah)

Package `engine/index/`.

| # | Task | Mode | Mins | Done when |
|---|---|---|---|---|
| B1 | `SqliteStore(IndexStore)`: tables `documents` (json) and `chunks` (json + embedding blob). On open, load all chunks into memory: `rank_bm25.BM25Okapi` over tokenised text, numpy matrix of embeddings. `bm25_search(q, k)`, `vector_search(vec, k)`, `upsert_document`, `upsert_chunks`, `get_document`, `list_documents`, `get_chunk`. Rebuild in-memory index after upsert | [H] | 40 | integration test: upsert 20 fake chunks with random vectors, both searches return expected ids |
| B2 | `hybrid_search(store, query, query_vec, filters, k)`: run both, Reciprocal Rank Fusion (k=60), apply filters `department`, `doc_type`, `include_superseded` (default false, superseded docs get score * 0.3 instead of removal so the badge can still show), return `SearchResult[]` | [A] after B1 | 20 | unit test on RRF math, filter test |
| B3 | `resolve_supersession(store)`: for every doc with `supersedes: [titles]`, fuzzy-match (rapidfuzz, ratio > 80) against existing titles, set target `status=superseded`, `superseded_by=doc_id`. Run at end of ingest | [A] | 15 | test with two docs where B supersedes A |
| B4 | `eval/run.py`: loads `eval/questions.json`, runs hybrid search, prints recall@5. Write 10 questions once the seed corpus exists | [A] | 15 | prints a number |
| B5 | **Stretch.** `PgVectorStore(IndexStore)` + docker compose | [A] | 60 | same integration test passes |

## Workstream C: API and answers  (Cyndia)

Package `api/`. FastAPI.

| # | Task | Mode | Mins | Done when |
|---|---|---|---|---|
| C1 | FastAPI app, CORS allow-all, `GET /health`, pydantic models in `api/models.py` mirroring `contracts/` exactly, store opened once at startup from `INDEX_PATH` | [A] | 15 | `uvicorn api.main:app` serves `/health` |
| C2 | `POST /search` -> embed query (A3) -> B2 -> `SearchResponse` | [A] after B2 | 10 | curl returns results on the seed corpus |
| C3 | `POST /ask`: search top 8, build prompt (chunks numbered [1]..[8] with title and page), call Claude on Bedrock via `AnthropicBedrockMantle` from the `anthropic` SDK, stream SSE, parse `[n]` markers into `citations[]` with chunk_id, doc_id, title, page. System prompt in `api/prompts/answer.md`: answer in the language of the question, cite every claim, say "Tidak dijumpai dalam dokumen / Not found in the documents" if chunks are irrelevant, never invent a circular number | [H] | 45 | three scripted questions give correct cited answers, one trick question is refused |
| C4 | `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/pages/{n}.png?highlight={chunk_id}`: render the page with PyMuPDF at 110 dpi; if `highlight` given, `page.search_for(first 120 chars of chunk text)` and draw yellow rects before rendering. Highlight is rendered server-side so the UI just shows an image | [A] | 25 | opening the URL in a browser shows the page with the passage highlighted |
| C5 | `POST /documents/upload` (multipart) -> save to `data/uploads/` -> `ingest_file` synchronously -> return `IngestResult`. S3 put is a one-line stretch | [A] after A6 | 15 | upload via curl then search finds it |

## Workstream D: UI, seed corpus, demo  (Lawrence)

Package `web/`. Next.js 14 + Tailwind. Start D4 first because it runs unattended.

| # | Task | Mode | Mins | Done when |
|---|---|---|---|---|
| D4 | **Seed corpus, start at 0:15.** Generate 15 synthetic Sarawak-agency documents as markdown with an LLM: 6 Malay, 6 English, 3 mixed. Types: circulars, SOPs, meeting minutes, guidelines. Include two pairs where the newer one says "Pekeliling ini menggantikan Pekeliling Bil. X/2022" (supersedes). Every doc has a department from `contracts/taxonomy.json`. Convert to PDF with `scripts/md_to_pdf.py` (fpdf2 or markdown-pdf). Rasterise 2 of them to image-only PDFs (PyMuPDF render then re-insert) so they count as scanned | [A] | 45 unattended | `samples/` has 15 PDFs, 2 scanned, 2 supersession pairs, a `samples/MANIFEST.md` listing each with its department and language |
| D1 | Scaffold: `pnpm create next-app web --ts --tailwind --app`, API client in `web/lib/api.ts` typed by hand from `contracts/` (no codegen, no time), `NEXT_PUBLIC_API_URL` | [A] | 15 | renders, calls `/health` |
| D2 | Search page `/`: query box, department `<select>` from taxonomy, result cards with title, page, snippet, tags, red "Superseded" badge when `status=superseded`, card click opens viewer | [A] against mock JSON | 30 | works on mock, then on real API |
| D3 | Ask page `/ask`: question box, streamed answer, citation chips `[1]` rendered as buttons that open the viewer at that page with highlight | [H] | 40 | end to end with C3 |
| D5 | Viewer: modal or `/doc/[id]?page=n&highlight=chunk` that shows the PNG from C4 with prev/next page | [A] | 20 | highlight visible |
| D6 | Department selector in the header, persisted in localStorage, sent as a filter on every search and ask. Label it "Viewing as: Jabatan ..." | [H] | 10 | changing department changes results |
| D7 | Demo script in `docs/DEMO.md`: Q1 in Malay against an English doc (bilingual), Q2 that returns a citation and opens the highlight, Q3 that hits a superseded circular and shows the badge plus the newer answer. Rehearse twice. Screen-record once as backup | [H] | 30 | file exists, recording exists |
| D8 | Deck, 7 slides: problem, who it is for, demo, how it works (one architecture diagram from `docs/BRAINSTORM.md`), AWS services used (S3, Textract, Bedrock Titan, Bedrock Claude), what is next (Cognito, OpenSearch, conflict detection), team | [H] | 30 | exported PDF |

---

## Dependencies

```
0:00  everyone: AGENTS.md, contracts/, uv sync, aws creds, bedrock access check
0:15  A1 A2 A5 [agents]   B1 [H]   C1 C4 [agents]   D4 [agent, long]  D1 D2 [agents]
      A3 A4 [H]                     C3 prompt draft [H]
0:45  A6 [H] needs A1-A5, B1
1:00  B2 B3 [agents] need B1       C2 [agent] needs B2, A3
1:30  === VERTICAL SLICE: A6 -> B1 -> C2/C3 -> D2/D3 on one real PDF ===
1:30  A7 Textract (time-boxed)     B4 [agent]   C5 [agent]   D3 D5 D6 [H/agents]
2:30  ingest full seed corpus, run eval, fix the worst retrieval miss
3:00  === FREEZE === D7 rehearse, D8 deck, everyone else: bugs only
3:30  recording, push, submit prep
```

Cross-team contract: the only things that cross workstream boundaries are the pydantic
models in `contracts/` and the `IndexStore` interface in `engine/index/store.py`. If you
need to change either, say so in the group chat before you do.

---

## Prompts

- Per-task agent prompts with exact signatures and tests: `docs/AGENT-PROMPTS.md`.
- Product prompts the code uses: `engine/ingest/prompts/tagger.md` (A4),
  `engine/ingest/prompts/figure.md` (stretch), `api/prompts/answer.md` (C3),
  `docs/prompts/D4-seed-corpus.md` (D4).

## Generic agent prompt

Fallback for a task not covered in `docs/AGENT-PROMPTS.md`. Replace the task ID.

```
You are working on the repo at <path>. Read AGENTS.md first, then docs/PLAN.md and find
task <ID>. Read every file under contracts/ that the task touches.

Implement task <ID> only. Do not edit files outside the package named in the task. Write
the test first, then make it pass. Run `uv run pytest <package>` (or `pnpm test` for web)
and paste the output. If something in another package is missing, stub it with a clearly
marked TODO(<workstream letter>) and keep going.

When done, reply with: the list of files changed, the test output, and anything you had to
assume. Do not commit.
```

The human then runs the tests, reads the diff, commits with `<area>: <what>`.
