# Plan

4 people, 4 hours.

- A Malissa: ingest, `engine/ingest/`
- B Noah: index and search, `engine/index/`
- C Cyndia: API, `api/`
- D Lawrence: UI, seed corpus, demo, `web/`

[A] means hand it to an agent with the matching block in `docs/AGENT-PROMPTS.md` and review
the diff. [H] means do it yourself. Tests use `engine/testing.py` (`FakeStore`,
`make_document`, `make_chunk`) so nobody waits for the real store. Set `EMBED_FAKE=1` to run
anything without AWS credentials.

## Who blocks whom

Three pieces gate other people. Push each to `dev-law` the moment it works and say so in the
chat. Everything else runs in parallel against `FakeStore` or mock JSON.

- B1 SqliteStore (Noah) unblocks A6, C4, C5, and the real store in C1.
- A3 embed_texts and A6 ingest_file (Malissa) unblock C2, C3, C5, and the first real data.
- C3 /ask (Cyndia) unblocks D3.

## Order of work

0:00
- Noah: B1 [H]. Push as soon as it works.
- Malissa: A1, A2 [A].
- Cyndia: C1 [A].
- Lawrence: D4, D1 [A].

0:30
- Noah: B2, B3 [A] on FakeStore.
- Malissa: A3, A5.
- Cyndia: C4 [A], draft the C3 prompt.
- Lawrence: D2 [A] on mock JSON.

0:45
- Noah: push B2.
- Malissa: A6 [H], pull B1 first.
- Cyndia: C2 [A] once B2 and A3 are pushed.
- Lawrence: D5 [A].

1:00
- Noah: B4 [A].
- Malissa: A4 [H].
- Cyndia: C3 [H] once A3 and B2 are pushed.
- Lawrence: D3 [H] once C3 is pushed.

1:30 Vertical slice on one machine. One PDF in, cited answer out, shown in the UI.

1:30 to 3:00
- Noah: tune ranking on real data, run eval at 2:30, fix the worst miss.
- Malissa: A7 Textract, 30 minute box, drop it at 2:00 if not working.
- Cyndia: C5 [A].
- Lawrence: D6, D5 polish, D7 demo script at 2:30.

3:00 Freeze. Bugs only. Lawrence does D8 deck.

3:30 Rehearse twice, record a backup.

## A: Ingest (Malissa)

- A1 [A] `extract_pages(path) -> list[Page]` with PyMuPDF. Text, blocks with bbox,
  `is_scanned` when a page has under 50 characters.
  Done: test PDF gives pages, bboxes, and the scanned flag.
- A2 [A] `chunk_pages(doc_id, pages) -> list[Chunk]`. Per page, 800 words, 100 overlap,
  keep page and first-block bbox.
  Done: short page gives 1 chunk, long page gives n, ids unique.
- A3 [H] `embed_texts(texts) -> np.ndarray`, 1024 dims, rows normalised. Titan v2 via boto3,
  batched, cached by sha256 in `~/.cache/rujuk/embed.sqlite`. Keep an `EMBED_FAKE=1` branch
  that returns deterministic hash-seeded vectors.
  Done: repeat call makes zero API calls.
- A4 [H] `tag_document(filename, text) -> dict` via Claude Haiku on Bedrock. Prompt and
  fallbacks in `engine/ingest/prompts/tagger.md`.
  Done: 5 seed docs tagged right by eye, bad JSON falls back, never fails ingest.
- A5 [A] `detect_lang(text)` and `extract_keywords(text, lang)` with langdetect and YAKE.
  Done: Malay and English samples come out right.
- A6 [H] `ingest_file(path, store) -> IngestResult`, idempotent on
  `doc_id = sha256(bytes)[:16]`. CLI `python -m engine.ingest <folder>` ingests all files
  then calls `resolve_supersession(store)` once.
  Done: runs over `samples/` and prints document and chunk counts.
- A7 [H] stretch, after 1:30, 30 minute box. Textract for `is_scanned` pages.
  Done: one scanned doc is searchable, or dropped at 2:00.

## B: Index (Noah)

- B1 [H] `SqliteStore(IndexStore)`, all 9 interface methods.
  SQLite opened with `check_same_thread=False`, WAL mode, an RLock around writes, parent
  folder created. BM25 in memory with a `BM25Okapi` subclass using the Lucene idf
  `log(1 + (N - n + 0.5) / (n + 0.5))`; skip the build when empty; drop scores at or
  below 0. numpy matrix of normalised vectors, skip null embeddings. Reads return copies
  without `embedding`. Reload when `PRAGMA data_version` changes so the API sees CLI ingests.
  Done: 20 fake chunks, both searches return expected ids; empty store returns `[]`;
  works from a second thread.
- B2 [A] `hybrid_search(store, query, query_vec | None, filters, top_k)`.
  Candidate pool 200 per list, or every chunk when a filter is set. RRF with k=60.
  Superseded chunks demoted by rank + 5, not by score, unless `include_superseded`.
  Department filter keeps that department or "Umum"; `None` or "Umum" means no filter.
  `query_vec=None` means BM25 only.
  Done: RRF math test, filter tests, a superseded chunk ranked first stays inside the top
  10 and below the current one.
- B3 [A] `resolve_supersession(store)`. A reference like `Bil. 2/2022` must share its
  number with the candidate title or filename before `partial_ratio >= 80` applies; a
  reference with no number uses fuzzy only. Year guard. Idempotent.
  Done: A superseded by B; a reference that matches nothing marks nothing; `1/2023` is not
  hit by a `2/2022` reference.
- B4 [A] `eval/run.py`. Questions keyed by `expected_filename`, `--bm25-only` flag, prints
  recall@5. Write 10 questions from `samples/MANIFEST.md` key facts, half cross-language.
  Done: prints a number.

## C: API (Cyndia)

- C1 [A] FastAPI, CORS open, `/health`, pydantic models in `api/models.py` mirroring
  `contracts/`. Lifespan opens `SqliteStore(INDEX_PATH)` and falls back to `FakeStore()`
  with a warning if B1 is not there yet.
  Done: `/health` returns 200.
- C2 [A] `POST /search`. Embed the query; on failure pass `query_vec=None`. Call B2.
  Done: curl returns results.
- C3 [H] `POST /ask`. Top 8 chunks, Claude Sonnet on Bedrock via `AnthropicBedrockMantle`,
  SSE stream, `[n]` markers mapped to citations. Prompt and post-processing in
  `api/prompts/answer.md`.
  Done: 3 scripted questions right, the trick question is refused, a superseded doc is
  named as superseded.
- C4 [A] `GET /documents`, `/documents/{id}`,
  `/documents/{id}/pages/{n}.png?highlight=chunk_id`. PyMuPDF render at 110 dpi, yellow
  rectangle on `search_for(first 120 chars of the chunk)`.
  Done: the browser shows the highlighted page.
- C5 [A] `POST /documents/upload`. Save to `data/uploads/`, `ingest_file`,
  `resolve_supersession`, return the result. S3 put is optional.
  Done: upload then search finds it.

## D: UI and demo (Lawrence)

- D4 [A] Seed corpus. Generate 15 docs with `docs/prompts/D4-seed-corpus.md`, convert with
  `scripts/md_to_pdf.py`, rasterise 2 as scans, write `samples/MANIFEST.md`.
  Done: 15 PDFs, 2 with no text layer, manifest present.
- D1 [A] Next.js scaffold, `lib/types.ts` and `lib/api.ts` from contracts, taxonomy
  constants, health placeholder page.
  Done: `pnpm build` passes.
- D2 [A] Search page. Query box, department select, result cards, red Superseded badge,
  click opens the viewer. Mock JSON until the API exists.
  Done: works on mock, then on the real API.
- D5 [A] Viewer `/doc/[id]?page=n&highlight=chunk`. Page PNG from C4, prev and next.
  Done: highlight visible.
- D3 [H] Ask page. Streamed answer, `[n]` chips open the viewer at that page.
  Done: end to end with C3.
- D6 [H] Department selector in the header, kept in localStorage, sent on every request.
  Done: changing it changes results.
- D7 [H] `docs/DEMO.md`. Q1 Malay question answered from an English doc. Q2 citation and
  highlight. Q3 superseded badge plus the current answer. Rehearse twice, record once.
  Done: file and recording exist.
- D8 [H] Deck, 7 slides: problem, users, demo, architecture, AWS services, next steps, team.
  Done: PDF exported.
