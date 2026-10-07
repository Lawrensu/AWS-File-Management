# Per-task agent prompts

One paste-ready prompt per [A] task. Every prompt assumes the agent is started in the repo
root and can read files. Replace nothing; the task text is complete. Human owner reviews the
diff and runs the tests before committing.

Common preamble, included at the top of every prompt below:

```
Read AGENTS.md, then contracts/README.md. Work only inside the package named below. Write
the test first, make it pass, run the test command, and paste its output. Do not commit.
Tests that need a store use engine.testing.FakeStore, make_document, make_chunk; never
SqliteStore. Reply with the list of files changed and anything you had to assume.
```

---

## A1 extract_pages (Malissa)

```
<preamble>

Package: engine/ingest/. Create engine/ingest/extract.py and engine/ingest/test_extract.py.

Implement:

    @dataclass
    class Block:
        text: str
        bbox: tuple[float, float, float, float]   # x0, y0, x1, y1 in PDF points, origin top-left

    @dataclass
    class Page:
        number: int          # 1-indexed
        text: str            # full page text, blocks joined with "\n"
        blocks: list[Block]
        is_scanned: bool     # True when len(text.strip()) < 50
        width: float
        height: float

    def extract_pages(path: str | Path) -> list[Page]

Use PyMuPDF (import fitz). Use page.get_text("blocks") and keep only text blocks (block type
0). Strip empty blocks. Sort blocks top-to-bottom then left-to-right.

Test: generate a 2-page PDF inside the test with fitz (page.insert_text) containing a known
sentence on page 1 and nothing on page 2. Assert page 1 text contains the sentence, page 1
has at least one block with a non-zero bbox, page 2 is_scanned is True, numbers are 1 and 2.

Test command: uv run pytest engine/ingest/test_extract.py -q
```

## A2 chunk_pages (Malissa)

```
<preamble>

Package: engine/ingest/. Create engine/ingest/chunker.py and engine/ingest/test_chunker.py.
Depends on Page and Block from engine/ingest/extract.py (create a stub with those two
dataclasses if the file does not exist yet, marked TODO(A1)).

Implement:

    def chunk_pages(doc_id: str, pages: list[Page], max_tokens: int = 800,
                    overlap: int = 100) -> list[dict]

Each returned dict matches contracts/chunk.schema.json with keys chunk_id, doc_id, page,
bbox, heading, text, lang, source. Set lang="en" and source="native" for now; A5 and A6
overwrite them. Set embedding to None.

Rules:
- Never merge text across pages. One page produces one or more chunks.
- Tokens = whitespace-separated words (no tiktoken, keep it dependency-free).
- A page with <= max_tokens words is one chunk. Longer pages split into windows of
  max_tokens with overlap words of overlap, stepping through the block list so bbox of the
  chunk is the bbox of the first block that contributes to it.
- heading: the last block before the chunk whose text is under 12 words and is either ALL
  CAPS or starts with a number pattern like "1.", "2.1", "BAHAGIAN", "PART", "SEKSYEN". None
  if no such block.
- chunk_id = f"{doc_id}:{page}:{n}" with n starting at 0 per page.
- Skip pages with empty text.

Tests: short page gives 1 chunk; a page with 2000 words gives 3 chunks with overlapping
boundaries; every chunk has page >= 1 and non-empty text; chunk ids are unique; a heading
block "2. KADAR ELAUN" is picked up as heading for the chunk after it.

Test command: uv run pytest engine/ingest/test_chunker.py -q
```

## A5 keywords and language (Malissa)

```
<preamble>

Package: engine/ingest/. Create engine/ingest/keywords.py and engine/ingest/test_keywords.py.

Implement:

    def detect_lang(text: str) -> str      # returns "ms", "en", or "mixed"
    def extract_keywords(text: str, lang: str, top_k: int = 10) -> list[str]

detect_lang: use langdetect.detect_langs. Map "ms" and "id" to "ms" (langdetect confuses
Malay and Indonesian). If the top two languages are ms/id and en and both have probability
above 0.3, return "mixed". Catch LangDetectException and return "en". Set
langdetect.DetectorFactory.seed = 0 at import for determinism.

extract_keywords: use yake.KeywordExtractor with lan = "ms" if lang in ("ms", "mixed") else
"en", n=2 (up to bigrams), dedupLim=0.9, top=top_k. Return the keyword strings only,
lowercased, deduplicated, in YAKE's order. Return [] for text under 20 words.

Tests: a 100-word Malay paragraph about "elaun perjalanan" and "tuntutan" returns lang "ms"
and keywords containing "elaun perjalanan" or "elaun"; an English paragraph about
"procurement threshold" returns "en" and a keyword containing "procurement"; empty text
returns [] without raising.

Test command: uv run pytest engine/ingest/test_keywords.py -q
```

## B2 hybrid_search (Noah)

```
<preamble>

Package: engine/index/. Create engine/index/hybrid.py and engine/index/test_hybrid.py.
Depends only on IndexStore in engine/index/store.py (exists). Test with
engine.testing.FakeStore.

Implement:

    @dataclass
    class Filters:
        department: str | None = None
        doc_type: str | None = None
        include_superseded: bool = False

    SUPERSEDED_RANK_OFFSET = 5

    def rrf(rankings: list[list[str]], k: int = 60,
            demoted: set[str] = frozenset()) -> dict[str, float]
        # score(id) = sum over rankings of 1 / (k + rank + offset), rank starting at 1,
        # offset = SUPERSEDED_RANK_OFFSET if id in demoted else 0

    def hybrid_search(store: IndexStore, query: str, query_vec: np.ndarray | None,
                      filters: Filters, top_k: int = 10) -> list[dict]

hybrid_search:
- Candidate pool: n = 200, or store.count()[1] (every chunk) when any filter field is set.
- Call store.bm25_search(query, n). If query_vec is not None also call
  store.vector_search(query_vec, n); with None, BM25 only.
- Load each candidate's chunk and document once. Drop candidates whose document fails a
  filter. Department filter: keep when filters.department is None or "Umum", or when
  doc["department"] equals it or equals "Umum". doc_type filter: keep when None or equal.
- demoted = chunk ids whose doc["status"] == "superseded", empty when include_superseded.
- Fuse with rrf, sort desc, take top_k. Return dicts matching SearchResult in
  contracts/api.md: chunk_id, doc_id, title, page, snippet, score, doc_type, department,
  status, superseded_by, lang. snippet = first 300 chars of chunk text.

Tests: rrf of [[a,b],[b,a]] gives a and b equal scores; rrf of [[a],[a]] > rrf of [[a],[b]]
for a; department filter removes other departments but keeps "Umum" docs; a superseded
chunk ranked 1st in both lists with 28 other candidates stays inside top 10 and below the
current chunk; include_superseded=True restores it to the top; query_vec=None returns
results from BM25 alone.

Test command: uv run pytest engine/index/test_hybrid.py -q
```

## B3 resolve_supersession (Noah)

```
<preamble>

Package: engine/index/. Create engine/index/supersession.py and
engine/index/test_supersession.py. Test with engine.testing.FakeStore.

Implement:

    def resolve_supersession(store: IndexStore) -> list[tuple[str, str]]
        # returns [(old_doc_id, new_doc_id)] pairs that were marked

For every document with a non-empty "supersedes" list, for each reference string in it:
- Extract a reference number with the regex (\d+)\s*/\s*(\d{4}) (for example "2/2022").
- Candidates are all other documents. If the reference has a number, keep only candidates
  whose title or filename contains that same "number/year" (allow "2/2022" and "2-2022").
  If the reference has no number, keep all candidates.
- Score candidates with rapidfuzz.fuzz.partial_ratio(reference, title). Take the best. Accept
  if score >= 80.
- Year guard: skip when both years are known and the candidate year >= the newer doc year.
- Set candidate status="superseded", superseded_by=newer doc_id, store.upsert_document.
Idempotent: running twice gives the same state and the same pairs.

Tests: doc A titled "Pekeliling Kewangan Bil. 2/2022" year 2022, doc B with
supersedes=["Pekeliling Kewangan Bil. 2/2022"] year 2024 gives A superseded by B; a
reference to "Bil. 2/2022" when only "Pekeliling Kewangan Bil. 1/2023" is indexed marks
nothing; the year guard stops a 2021 doc superseding a 2023 doc; running twice is stable.

Test command: uv run pytest engine/index/test_supersession.py -q
```

## B4 eval runner (Noah)

```
<preamble>

Package: eval/. Create eval/run.py. Do not write tests for this one; it is a script.

Read eval/questions.json, a list of {"question": str, "expected_filename": str}. Open
SqliteStore(os.environ.get("INDEX_PATH", "data/index.sqlite")). For each question, embed it
with engine.ingest.embed.embed_texts unless the --bm25-only flag is given (then pass
query_vec=None), run engine.index.hybrid.hybrid_search with empty Filters and top_k=5, and
count a hit when any result's document filename equals expected_filename. Print one line per
question with HIT or MISS and the top result filename, then "recall@5 = X/N (P%)".

Also rewrite eval/questions.json with 10 questions taken from the key_fact column of
samples/MANIFEST.md: 5 in Malay, 5 in English, and make at least 4 of them target a document
written in the other language.

Run: uv run python eval/run.py --bm25-only
```

## C1 FastAPI skeleton and models (Cyndia)

```
<preamble>

Package: api/. api/main.py exists with a /health route and a lifespan stub. Create
api/models.py and api/test_health.py, and finish the lifespan.

api/models.py: pydantic v2 models mirroring contracts exactly. Document and Chunk from the
two schema files (Chunk without the embedding field). SearchFilters, SearchRequest,
SearchResult, SearchResponse, AskRequest, Citation, AskResponse, UploadResponse, and
HealthResponse from contracts/api.md. Use Literal types for the enums.

Lifespan: open engine.index.store.SqliteStore(os.environ.get("INDEX_PATH",
"data/index.sqlite")) and set app.state.store. If that raises NotImplementedError (B1 not
done yet), set app.state.store = engine.testing.FakeStore() and log a warning.

Test: with fastapi.testclient, GET /health returns 200 and a body with ok=True.

Test command: uv run pytest api/test_health.py -q
```

## C2 POST /search (Cyndia)

```
<preamble>

Package: api/. Create api/search.py and api/test_search.py. Register the router in
api/main.py.

POST /search takes SearchRequest, embeds request.query with
engine.ingest.embed.embed_texts([query])[0]; if that raises, log it and use query_vec=None
(BM25 only). Call engine.index.hybrid.hybrid_search with Filters built from request.filters
and top_k=request.top_k (default 10, max 50), and return SearchResponse.

Test: monkeypatch embed_texts and hybrid_search to return fixed values and assert the
response shape matches SearchResponse.

Test command: uv run pytest api/test_search.py -q
```

## C4 documents and page render (Cyndia)

```
<preamble>

Package: api/. Create api/documents.py and api/test_documents.py. Register the router.

Routes per contracts/api.md:
- GET /documents -> {"documents": [Document...]} from store.list_documents().
- GET /documents/{doc_id} -> Document plus "chunks": store.chunks_for_document(doc_id)
  with embedding removed. 404 if unknown.
- GET /documents/{doc_id}/pages/{page}.png?highlight=<chunk_id>:
  open the file at doc["source_path"] with fitz, 404 if page out of range. If highlight is
  given, load the chunk, take the first 120 characters of its text, call
  page.search_for(that_text); if no hits, retry with the first 60 characters; for each hit
  rect call page.draw_rect(rect, color=(1, 0.85, 0), fill=(1, 0.85, 0), fill_opacity=0.35,
  width=0). Render with page.get_pixmap(dpi=110) and return image/png bytes with
  Cache-Control: public, max-age=3600.

Test: generate a one-page PDF with fitz containing "KADAR ELAUN PERJALANAN RM0.70", register
it via a fake store in the test, request the PNG with and without highlight, assert 200,
content-type image/png, and the highlighted PNG differs in bytes from the plain one.

Test command: uv run pytest api/test_documents.py -q
```

## C5 upload (Cyndia)

```
<preamble>

Package: api/. Create api/upload.py and api/test_upload.py. Register the router.

POST /documents/upload: multipart field "file", accept .pdf only (400 otherwise), save to
data/uploads/<sha256[:16]>.pdf, call engine.ingest.pipeline.ingest_file(path,
app.state.store) (stub with TODO(A6) returning a fake IngestResult if absent), then call
engine.index.supersession.resolve_supersession(store), and return UploadResponse. If
S3_BUCKET is set, also boto3 put_object to s3://S3_BUCKET/uploads/<name> and set
source_path to the s3 URI in the returned doc; failures there log a warning, do not fail
the upload.

Test: monkeypatch ingest_file, post a small PDF, assert 200 and the response has doc_id.

Test command: uv run pytest api/test_upload.py -q
```

## D1 Next.js scaffold (Lawrence)

```
<preamble>

Package: web/. Run: pnpm create next-app web --ts --tailwind --app --eslint --no-src-dir
--import-alias "@/*" (accept defaults). Then:

- web/lib/types.ts: hand-written TypeScript types mirroring contracts/api.md (SearchRequest,
  SearchResult, SearchResponse, AskRequest, AskResponse, Citation, Document) and
  contracts/document.schema.json.
- web/lib/api.ts: fetch wrappers search(req), ask(req) (non-streaming for now), documents(),
  document(id), pageImageUrl(docId, page, highlightChunkId?), health(). Base URL from
  process.env.NEXT_PUBLIC_API_URL with fallback http://localhost:8000.
- web/lib/taxonomy.ts: export the department list copied from contracts/taxonomy.json.
- app/page.tsx: placeholder that calls health() and shows "API: ok, N documents" or the
  error.
- web/.env.local.example with NEXT_PUBLIC_API_URL.

Verify: pnpm dev starts and the page shows the health line (or a clean error if the API is
down).
```

## D2 search page (Lawrence)

```
<preamble>

Package: web/. Build app/page.tsx as the search page, using components in web/components/.

- SearchBar: text input + submit, Enter submits.
- Department select in the header from lib/taxonomy.ts, default "Umum". Value stored in
  localStorage key "rujuk.department" and passed as filters.department. (D6 will reuse this.)
- ResultCard: title, "page N", snippet, small tag pills for doc_type and department, and a
  red pill "Superseded" when status === "superseded". Click navigates to
  /doc/[doc_id]?page=N&highlight=<chunk_id>.
- Loading and empty states. Tailwind only, no component library.
- Until the API exists, read from web/mock/search.json (create it with 3 results, one
  superseded) when NEXT_PUBLIC_USE_MOCK=1.

Verify: pnpm dev, search renders mock results, the superseded badge shows on one card.
```

## D5 page viewer (Lawrence)

```
<preamble>

Package: web/. Create app/doc/[id]/page.tsx.

Reads query params page (default 1) and highlight (optional). Loads document(id) for the
title and page_count. Shows the title, "Page N of M", prev/next buttons, and an <img> with
src = pageImageUrl(id, page, highlight). Keep highlight in the URL only for the page it was
given for; prev/next drop it. Simple centered layout, image max-width 900px.

Verify: open /doc/<any id>?page=1 against the mock or real API; the image loads or a clean
404 message shows.
```

## D4 seed corpus (Lawrence, run first, unattended)

Use `docs/prompts/D4-seed-corpus.md` for the document generation. Then give an agent this:

```
<preamble>

Package: scripts/ and samples/. The folder samples/src/ contains 15 markdown files with YAML
front matter (filename, doc_type, department, lang, year, supersedes, scanned). Write
scripts/md_to_pdf.py that converts each one to samples/<name>.pdf using fpdf2 with the
bundled DejaVu font: front matter stripped, "# " headings as bold 14pt, "## " as bold 12pt,
paragraphs as 11pt with 6pt spacing, lists as indented lines, tables as monospace lines.
For files with scanned: true, open the produced PDF with fitz, render each page at 150 dpi,
and write a new PDF made only of those images (fitz: new doc, insert_image on a page of the
same size), overwriting the text version. Finally write samples/MANIFEST.md as a table of
filename, doc_type, department, lang, year, supersedes, scanned.

Verify: uv run python scripts/md_to_pdf.py produces 15 PDFs; fitz reports zero text on the
two scanned ones and non-empty text on the rest.
```
