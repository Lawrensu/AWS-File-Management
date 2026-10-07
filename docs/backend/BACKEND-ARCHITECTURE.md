# Backend Architecture

This document describes how the Rujuk backend is organised and where each part comes from:
- how each backend layer is derived from the functional requirements
- the data model (document and chunk)
- the ingest pipeline, the index and search, and the LLM providers
- the prompts, the routes and the error conventions
- what exists today and what is still planned

- Functional requirements are in [System Design](../SYSTEM-DESIGN.md)
- Shapes are in [contracts](../../contracts/README.md)
- Rules are in [AGENTS.md](../../AGENTS.md)

Built today: `engine/index/`, `engine/testing.py`, `eval/run.py`, `GET /health`. Everything marked (planned) is not built.

---

# Overview

## Backend Repo Structure

Separation of concerns:
- `engine/` owns data and search
- `api/` owns HTTP
- Everything crosses through `IndexStore` and the shapes in `contracts/`

```
engine/ingest/            A. File to chunks with text, page, bbox, keywords, tags, embedding
	__init__.py             exists, docstring only (module list)
	prompts/tagger.md       exists, tagger prompt and validation rules
	extract.py              (planned) A1 PyMuPDF pages and blocks
	chunker.py              (planned) A2 page chunks
	embed.py                (planned) A3 Cohere embeddings on Bedrock, cached
	tagger.py               (planned) A4 Claude Haiku tags
	keywords.py             (planned) A5 language and YAKE keywords
	pipeline.py             (planned) A6 ingest_file and the CLI
	textract.py             (planned) A7 stretch, OCR for scanned pages
engine/index/             B. Done
	store.py                IndexStore interface and SqliteStore
	hybrid.py               hybrid_search, Filters, RRF, language-aware fusion
	supersession.py         resolve_supersession
	README.md               B notes, ahead of PLAN and SYSTEM-DESIGN
engine/testing.py         FakeStore, make_document, make_chunk for every test
engine/llm.py             exists, the one LLM entry point: Bedrock first, Groq fallback
engine/test_llm.py        exists, stub clients only
api/                      C. FastAPI
	main.py                 exists: app, CORS, lifespan placeholder, /health
	prompts/answer.md       exists, answer prompt and post-processing rules
	models.py               (planned) pydantic models mirroring contracts/
	search.py               (planned) POST /search
	ask.py                  (planned) POST /ask
	documents.py            (planned) GET /documents routes and page PNG
	upload.py               (planned) POST /documents/upload
eval/                     B4. run.py prints recall@5 over questions.json
```

## Derivation

Derivation order (each step only depends on the steps before it):
1. Functional requirement, from [System Design](../SYSTEM-DESIGN.md)
2. Contracts (`contracts/*.json`, `contracts/api.md`)
3. Engine function (ingest or index)
4. Route
5. Response model (pydantic, in `api/models.py`, planned)

- Every engine function and route must trace back to a requirement in System Design
- No undocumented fields in API responses

## Notes

Worked example, the supersession demo (demo Q3 in `docs/DEMO.md`):
- Requirement: supersession is detected at ingest, the old document is badged and ranked lower, and staff are never given an outdated rate
- Contract fields: Document `supersedes`, `superseded_by`, `status`, `year`, `title`. Search result `status`, `superseded_by`. Citation `status`
- Engine functions:
	- `tag_document` (planned, A4) reads "supersedes" from the text, for example `["Pekeliling Kewangan Bil. 2/2022"]` on the 2024 circular
	- `ingest_file` (planned, A6) stores the document, then the CLI calls `resolve_supersession(store)` once after the last file
	- `resolve_supersession` matches the reference to the 2022 circular's title, sets its `status` to `superseded` and `superseded_by` to the 2024 `doc_id`
	- `hybrid_search` demotes the old chunks by 5 ranks and keeps them in the results
- Route: `POST /search` (planned) for the badge. `POST /ask` (planned) for the answer, where the prompt labels the excerpt `SUPERSEDED by <title>`, read with `store.get_document(superseded_by)`
- UI: the 2024 circular ranks first, the 2022 circular shows a red Superseded badge, and the Ask answer gives RM0.70 per km and notes that the 2022 rate was superseded

---

# Implementation Details

## Data Model

Source of truth is `contracts/document.schema.json` and `contracts/chunk.schema.json`. Both set `additionalProperties: false`.

### Document

Required: `doc_id`, `title`, `filename`, `doc_type`, `department`, `lang`, `status`, `page_count`
- `doc_id: str` first 16 hex of sha256 of the file bytes
- `title: str` extracted by the tagger from the first page, falls back to the filename
- `doc_type: str` one of `taxonomy.doc_type`
- `department: str` one of `taxonomy.department`
- `topics: list[str]` optional, subset of `taxonomy.topic`
- `filename: str` and `source_path: str` (optional, local path or `s3://bucket/key`)
- `year: int | null`
- `lang: str` `ms`, `en` or `mixed`
- `status: str` `current`, `superseded` or `draft`
- `supersedes: list[str]` titles or reference numbers as written in the document, resolved to doc_ids by `resolve_supersession`
- `superseded_by: str | null` doc_id of the newer document, set by `resolve_supersession`
- `keywords: list[str]` YAKE top 10, `page_count: int` at least 1, `has_scanned_pages: bool` default false, `ingested_at: str` date-time

### Chunk

Required: `chunk_id`, `doc_id`, `page`, `text`, `lang`, `source`
- `chunk_id: str` pattern `{doc_id}:{page}:{n}`
- `doc_id: str`
- `page: int` 1-indexed, at least 1, mandatory, citations depend on it
- `heading: str | null` nearest heading above the chunk, if detected, and `source: str` `native`, `textract` or `vision`
- `bbox: [x0, y0, x1, y1] | null` PDF points, origin top-left, of the first text block in the chunk
- `text: str` not empty
- `lang: str` `ms`, `en` or `mixed`
- `embedding: list[float] | null` 1024 floats from Cohere Embed Multilingual v3, stored, never returned by the API

Id conventions:
- `doc_id` is the sha256 of the file bytes, first 16 hex, so ingest is idempotent
- `chunk_id` is `{doc_id}:{page}:{n}`, n counts from 0 per page, pages are 1-indexed

## Ingest Pipeline (planned)

Code in `engine/ingest/`, none of it is built yet. Steps from PLAN A1 to A7:
1. A1 `extract_pages(path: str | Path) -> list[Page]` with PyMuPDF, text and blocks with bbox, `is_scanned` when a page has under 50 characters
2. A2 `chunk_pages(doc_id: str, pages: list[Page], max_tokens: int = 800, overlap: int = 100) -> list[dict]` per page, 800 words with 100 overlap, keeps page and first-block bbox
3. A3 `embed_texts(texts, input_type="document") -> np.ndarray` 1024 dims, rows normalised, Cohere Embed Multilingual v3 via boto3 `invoke_model` in `ap-southeast-1`, batches of 96, cached by sha256 of model, input type and text in `~/.cache/rujuk/embed.sqlite`, `EMBED_FAKE=1` returns deterministic hash-seeded vectors
4. A4 `tag_document(filename, text) -> dict` Claude Haiku on Bedrock, prompt in `engine/ingest/prompts/tagger.md`, bad JSON falls back, never fails ingest
5. A5 `detect_lang(text) -> str` and `extract_keywords(text, lang, top_k=10) -> list[str]` with langdetect and YAKE
6. A6 `ingest_file(path, store) -> IngestResult` idempotent on `doc_id`, CLI `python -m engine.ingest <folder>` ingests all files, then calls `resolve_supersession(store)` once
7. A7 stretch, Textract for `is_scanned` pages, 30 minute box, dropped at 2:00 if not working

Rules from `engine/index/README.md` that A must match:
- A2 writes `lang="en"` as a placeholder, A6 must overwrite it with `detect_lang`, otherwise language-aware fusion treats every chunk as English
- The tagger must copy the printed title with its reference number, for example "Pekeliling Kewangan Bil. 2/2022", because supersession matches on the number

## Index and Search

Code in `engine/index/`. All access goes through `IndexStore`.

`IndexStore` methods (9):
- `upsert_document(doc)`
- `upsert_chunks(chunks)` replaces existing chunks for the same doc_id
- `get_document(doc_id) -> Document | None`
- `list_documents() -> list[Document]`
- `get_chunk(chunk_id) -> Chunk | None`
- `chunks_for_document(doc_id) -> list[Chunk]`
- `bm25_search(query, k) -> list[(chunk_id, score)]` best first
- `vector_search(query_vec, k) -> list[(chunk_id, score)]` cosine, best first
- `count() -> (documents, chunks)`

`SqliteStore` (`store.py`):
- SQLite with two tables, `documents` and `chunks`, each row a JSON blob, embeddings as float32 blobs
- Threading: one connection opened with `check_same_thread=False`, every access under an `RLock`, so the FastAPI thread pool can share it
- WAL mode and `synchronous=NORMAL`, parent folder created, `close()` available
- BM25 in memory with a `BM25Okapi` subclass using the Lucene idf `log(1 + (N - n + 0.5) / (n + 0.5))`, always positive, so a one-PDF index still gets keyword hits
- Vectors held as a numpy matrix of L2-normalised rows, null embeddings skipped
- Reload when `PRAGMA data_version` changes, so the API sees a CLI ingest without a restart
- Reads return copies, and chunks never carry `embedding`
- `upsert_chunks` raises `ValueError` on a missing or zero page, a duplicate `chunk_id` in one call, or an embedding whose dimension differs from the index
- Bilingual stopwords: Malay and English function words are dropped from BM25 at index and query time, English "had" is kept because it means "limit" in Malay

`FakeStore` (`engine/testing.py`):
- Complete in-memory `IndexStore` for tests, `bm25_search` is plain term overlap, not BM25
- Every test uses these, except `test_store.py`, which tests `SqliteStore`

`hybrid_search(store, query, query_vec, filters, top_k=10)` (`hybrid.py`):
- `Filters`: `department`, `doc_type`, `include_superseded` (default false)
- Candidate pool: 200 per list, or every chunk when a department or doc_type filter is set
- RRF with k=60, `score = sum 1 / (k + rank + offset)`
- Superseded chunks are demoted by rank, offset 5, not by score, unless `include_superseded`
- Department filter keeps that department or `Umum`, `None` or `Umum` means no filter
- Filters run before fusion, so ranks count only what the viewer may see
- `query_vec=None` means BM25 only, used when embedding fails or `EMBED_FAKE=1`
- Language-aware fusion (`CROSS_LANGUAGE_OFFSET = 5`), only with a query vector:
	- `query_language` returns `ms` or `en` when langdetect is at least 90% sure, else None, and maps langdetect's `id` to `ms`
	- A chunk in another language gets its keyword rank set to its vector rank plus 5, or keeps its real keyword rank if that is better
	- `mixed` chunks count as another language for both
	- Unclear query language (short queries often) or no vector falls back to plain RRF
- `snippet` has whitespace collapsed, cut at 300 characters from the start of the chunk

`resolve_supersession(store) -> list[(old_doc_id, new_doc_id)]` (`supersession.py`):
- Runs once after ingest and after every upload
- Recomputes from scratch on every run, so it is idempotent and clears a mark whose reference has gone
- Match is against the candidate's title or filename stem, `partial_ratio >= 80`
- A reference with a number, like `Bil. 2/2022`, must share that number with the candidate first, a leading zero is accepted, `12/2022` and `1/2023` do not match `2/2022`
- A reference with no number uses fuzzy matching only
- Year guard: a candidate whose year is at or after the newer document's year is skipped

## LLM Providers

- `engine/llm.py` is the one LLM entry point. Every model call goes through it, and nothing else imports `anthropic` or `groq`
- Interface:
	- `complete(system, user, *, role, max_tokens, json_schema=None) -> LLMResult`, where `role` is `"tag"` or `"answer"` and `LLMResult` has `text`, `provider`, `model`, `input_tokens`, `output_tokens`
	- `stream(system, user, *, role, max_tokens) -> StreamResult`, iterate it for text deltas, read `.provider` and `.model` for who is answering. It returns after the first token has arrived
	- `preferred_provider(role) -> "bedrock" | "groq"`, what the next call will try first. `/ask` uses it to send 8 chunks to Bedrock or 5 to Groq
	- `LLMUnavailable` is raised when no provider is available or every one tried failed. Callers decide what to do: the tagger returns its fallback tags
- Provider order is Bedrock first, then Groq:
	- Bedrock is skipped when `EMBED_FAKE=1`, which means there is no AWS on this machine
	- Groq is skipped when `GROQ_API_KEY` is empty
	- Fallback to the next provider happens only before the first token. If Bedrock fails mid-stream, the exception is raised
- Circuit breaker: after a Bedrock failure for a role, Bedrock is skipped for that role for `LLM_BEDROCK_COOLDOWN` seconds (default 300), so every call does not pay the failure latency. The cooldown is ignored when Groq is not available, because there is nothing else to try
- `BEDROCK_CLIENT` picks the Bedrock client:
	- `mantle` (default): the `anthropic` SDK's `AnthropicBedrockMantle(aws_region=AWS_REGION)`
	- `converse`: boto3 `bedrock-runtime` `converse` and `converse_stream`
- Config comes from `.env`, never hardcoded: `AWS_REGION`, `BEDROCK_TAG_MODEL` (Claude Haiku), `BEDROCK_ANSWER_MODEL` (Claude Sonnet), `GROQ_TAG_MODEL`, `GROQ_ANSWER_MODEL`, `GROQ_API_KEY`, `BEDROCK_CLIENT`, `LLM_BEDROCK_COOLDOWN`. The defaults in `engine/llm.py` are only for unset variables. Both Groq models are `openai/gpt-oss-120b`
- `openai/gpt-oss` models reason before they answer, and reasoning tokens count against `max_tokens`. On Groq they run with `reasoning_effort` `low`, and `max_tokens` has a floor of 1024 for `tag` and 2048 for `answer`, so the visible answer is not cut off. Other Groq models get neither
- `json_schema` on Groq turns on JSON mode (`response_format` `json_object`) and appends a one-line instruction to return only JSON with the schema's keys. Bedrock gets the same one-line instruction, not a native structured-output request, so callers still parse and validate
- Current state: Claude on Bedrock is blocked for the AWS account until the Anthropic use case form is approved. Mantle returns 404 "model does not exist" and Converse returns "use case details have not been submitted". Groq serves every tag and answer today. Once the form is approved, Bedrock takes over with no code change
- No embedding fallback, search drops to BM25 only (`query_vec=None`). Embeddings are not an LLM call and stay in `engine/ingest/embed.py`
- On Groq, `/ask` uses the top 5 chunks instead of 8, to fit the free tier's token limit
- A Bedrock failure must never crash ingest or the API
- Embeddings use Cohere request fields `texts`, `input_type` and `truncate: END`
- Documents embed with `input_type="document"` (`search_document`), the default. API code embeds questions with `input_type="query"` (`search_query`). The two are cached separately
- Cohere on Bedrock rejects a text longer than 2048 characters. `embed_texts` trims each text to its first 2048 characters before sending, so the embedding covers the first 2048 characters of a chunk and BM25 covers all of it. The stored chunk text is unchanged. Titan inputs are not trimmed. Seed-corpus chunks run up to about 2450 characters, so some are trimmed
- A model ID starting with `amazon.titan` switches `embed_texts` back to the Titan v2 request, one text per call, so going back is a config change
- Only Lawrence's machine has model access, AWS and Groq. The vertical slice, the demo and real end to end tests run there. Elsewhere `engine.llm` raises `LLMUnavailable`, which is expected, and tests stub `engine.llm` and `embed_texts`

## Prompts

- `engine/ingest/prompts/tagger.md` (task A4): one call per document with the filename and first 3 pages capped at 6000 characters, choose only from the taxonomy, copy reference numbers exactly, return title, doc_type, department, topics, year, lang, supersedes and summary as JSON
	- Validation: off-taxonomy values are replaced with fallbacks, bad JSON retries once, then falls back to `other`, `Umum`, `lain`, empty `supersedes` and filename as title
- `api/prompts/answer.md` (task C3): top 8 numbered excerpts, answer in the question's language, use only the excerpts, end each fact with `[n]`, mark superseded excerpts and prefer the current one, reply with an exact not-found sentence otherwise
	- Post-processing: collect `[n]` in 1..8, build citations with `quote` as the first 200 characters, set `not_found`, `confidence` and `language`

## Routes

Same shapes as `contracts/api.md`. Base URL from `NEXT_PUBLIC_API_URL`, all JSON, CORS open. No auth.
Only `/health` exists today, every other route is planned.

```
GET /health                                      (exists, returns 0 and 0 until the store is attached)
	-> 200 {ok, documents, chunks}

POST /search                                     (planned, C2)
	Body: {query, filters?: {department?, doc_type?, include_superseded?}, top_k?}
	-> 200 {results: [{chunk_id, doc_id, title, page, snippet, score, doc_type, department, status, superseded_by, lang}]}

POST /ask                                        (planned, C3)
	Body: {question, filters?, top_k?, stream?}
	-> 200 {answer, language, confidence, citations: [{n, chunk_id, doc_id, title, page, status, quote}], not_found}
	-> 200 text/event-stream when stream is true, events {type: "token", text} then {type: "done", answer}

GET /documents                                   (planned, C4)
	-> 200 {documents: [Document]}

GET /documents/{doc_id}                          (planned, C4)
	-> 200 Document plus chunks without embedding

GET /documents/{doc_id}/pages/{page}.png?highlight={chunk_id}   (planned, C4)
	-> 200 PNG at about 110 dpi, highlighted passage as a translucent yellow rectangle
	-> 404 page out of range

POST /documents/upload                           (planned, C5)
	Body: multipart form, field file
	-> 200 {doc_id, title, pages, chunks, status, department}
```

## Error Conventions

Taken from `contracts/api.md`, which is short on codes:
1. All errors are `{"error": "<message>"}` with a 4xx or 5xx status
2. 200 for every success, including `/ask` when the answer is not found (`not_found: true`)
3. 404 when a page is out of range on the page PNG route
4. Other 4xx and 5xx codes are not specified yet (see Open Questions)

## Traceability

Requirement names follow [System Design](../SYSTEM-DESIGN.md). A planned item is marked.
- Extract text and blocks, send scanned pages to Textract: `extract_pages` (planned) -> none, internal to ingest -> none
- Chunk by page at 800 words with 100 overlap: `chunk_pages` (planned) -> none -> `Chunk`
- Extract keywords and detect language: `extract_keywords`, `detect_lang` (planned) -> none -> `Document.keywords`, `lang`
- Tag from a closed taxonomy and find what a document supersedes: `tag_document` (planned) -> none -> `Document` fields
- Embed with Cohere Embed Multilingual v3: `embed_texts` (planned) -> none -> embedding never returned
- Write to the index, idempotent on `doc_id`: `ingest_file` (planned), `IndexStore.upsert_document`, `upsert_chunks` -> `POST /documents/upload` (planned) -> upload response
- Resolve supersession after the whole folder: `resolve_supersession` -> `POST /documents/upload` (planned) -> `status`, `superseded_by`
- Search by meaning in both languages: `embed_texts` (planned), `hybrid_search`, `bm25_search`, `vector_search` -> `POST /search` (planned) -> `SearchResult`
- Department filter keeps that department or Umum: `hybrid_search` with `Filters.department` -> `POST /search`, `POST /ask` (planned) -> `SearchResult`
- Superseded documents are badged and ranked lower: `hybrid_search`, `resolve_supersession`, `get_document` -> `POST /search`, `POST /ask` (planned) -> `status`, `superseded_by`
- Cited answers in the question's language: `hybrid_search`, `get_chunk`, `get_document` -> `POST /ask` (planned) -> `AskResponse`, `Citation`
- Page opens with the passage highlighted: `get_chunk` (bbox, page, text) -> `GET /documents/{id}/pages/{n}.png` (planned) -> PNG

## Evaluation

- `eval/run.py` prints recall@5 of `hybrid_search` over `eval/questions.json`
- Questions are `{question, expected_filename}`, compared by filename stem, so a manifest `.md` matches the indexed `.pdf`
- Embeds every question in one batched call through `engine.ingest.embed.embed_texts` (planned), falls back to BM25 only if that module is missing
- `--bm25-only` skips embeddings and needs no AWS, `EMBED_FAKE=1` also runs BM25 only
- B notes: BM25 only recall@5 is 5/10 on the seed corpus, real Cohere vectors not measured yet

---

# TODO (future)

- Build `engine/ingest/` A1 to A6, then A7 Textract as a stretch
- Build `api/` C1 to C5, and `api/models.py`
- Run the eval with real Cohere vectors and tune `CROSS_LANGUAGE_OFFSET` (planned for 2:30)

---

# Open Questions

- `contracts/api.md` says `confidence` is `high` or `low`, `api/prompts/answer.md` also uses `medium`
- The `/ask` threshold of 0.03 sits near the ceiling of 0.0328, and BM25 only tops out at 0.0164 so no answer is ever high there (from the B notes)
- The tagger prompt returns a `summary` stored on the document for the UI card, but `document.schema.json` has no `summary` field and sets `additionalProperties: false`
- Tagger: a Groq `json_validate_failed` (HTTP 400) is retried once inside the tagger. Fallback: it now calls `engine.llm.complete`, which tries Bedrock then Groq, and falls back to default tags on `LLMUnavailable`. `tagger.md` still describes only the retry and the defaults
- `tag_document` is `(filename, text) -> dict` in PLAN, `(title, text) -> DocMeta` in `engine/ingest/__init__.py`, and `tagger.md` passes filename and text
- PLAN C1 says fall back to `FakeStore` if B1 is missing, the B notes say that fallback is no longer needed. `api/main.py` still sets `app.state.store = None` (TODO(C1)), so `/health` reports 0 and 0
- `api/main.py` docstring lists `models.py`, `search.py`, `ask.py`, `documents.py`, `upload.py`, none exist
- The error format is `{"error": ...}` but FastAPI's default is `{"detail": ...}`, a handler is needed and none exists. Status codes for upload failures, unknown `doc_id` and bad requests are not in the contract
- The year guard blocks a same-year supersession (Bil. 3/2024 replacing Bil. 1/2024), a known limitation in the B notes
- `docs/SYSTEM-DESIGN.md` does not yet mention stopwords, language-aware fusion or auto-reload, per the B notes
- `AGENTS.md` docs convention says one H1 and no H3, this doc follows the requested multi-part structure instead
