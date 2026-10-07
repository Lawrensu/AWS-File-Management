# engine/index: Workstream B notes

Owner: Noah. Last updated 2026-10-07.

Read this before merging a branch that touches ingest, the API, or the demo. The code here
is ahead of `docs/PLAN.md` and `docs/SYSTEM-DESIGN.md`. This file lists what changed beyond
the plan and what A, C and D need to match.

## Status

- B1 `SqliteStore`: done (`store.py`).
- B2 `hybrid_search`: done, plus two ranking changes from tuning (`hybrid.py`).
- B3 `resolve_supersession`: done (`supersession.py`).
- B4 eval runner and 10 questions: done (`eval/run.py`, `eval/questions.json`).
- Tests: 52 passing, all on `FakeStore` except `test_store.py`, which tests `SqliteStore`.
- Not done: the eval with real Cohere vectors. It needs AWS, so it runs on Lawrence's machine
  at 2:30.

## Ahead of the plan

None of these change `contracts/` or the `IndexStore` method signatures.

- Bilingual stopwords. Malay and English function words are dropped from BM25 at index
  and query time. On the seed corpus, the two English questions about Malay circulars
  ("car mileage", "passwords") went from 11 and 10 false keyword hits to 1 and 0. English
  "had" is kept, because in Malay it means "limit".
- Language-aware fusion (`CROSS_LANGUAGE_OFFSET = 5`). Keyword search cannot match a chunk
  in another language, and on a small corpus every keyword hit also has a vector rank, so
  it collects two votes. A cross-language answer that only vectors find then loses to any
  keyword hit. When langdetect is at least 90% sure the query is Malay or English, a chunk
  in another language gets its keyword rank set to its vector rank plus 5, or keeps its
  real keyword rank if that is better. "mixed" chunks count as another language for both.
  If the query language is unclear (short queries often are) or there is no query vector,
  ranking falls back to plain RRF.
- Auto-reload. Every read checks `PRAGMA data_version` and reloads when another process
  has written. The API sees a CLI ingest without a restart.
- Store validation. `upsert_chunks` raises `ValueError` on a missing or zero page, a
  duplicate `chunk_id` in one call, or an embedding whose dimension differs from the index.
- Filters run before fusion, so ranks count only what the viewer may see. The candidate
  pool is 200 per list, or every chunk when a department or doc_type filter is set.
- B3 recomputes from scratch on every run. It clears a "superseded" mark whose reference
  has gone, the newest replacement wins, it fuzzy-matches against the title or the filename
  stem, and it accepts a leading zero ("02/2022").
- Snippets have whitespace collapsed before the 300-character cut.
- The eval compares filenames by stem (so the manifest's `.md` matches the indexed `.pdf`),
  embeds every question in one Bedrock call, and runs BM25 only under `EMBED_FAKE=1`.

## What other workstreams need to match

### A, ingest (Malissa)

- Call `resolve_supersession(store)` once at the end of the ingest CLI, after every file.
- Set `lang` on every chunk with `detect_lang`. A2 writes `"en"` as a placeholder. If A6
  does not overwrite it, the language-aware fusion treats every chunk as English, and
  Malay questions lean on vectors alone.
- The tagger must copy the printed title with its reference number, e.g. "Pekeliling
  Kewangan Bil. 2/2022". B3 links a "supersedes" reference only to a title or filename with
  the same number. Both superseded seed documents print the number in their heading.
- `upsert_chunks` raises `ValueError` on bad data (see above). Those are A2 bugs to fix,
  not errors to swallow.
- Embeddings can be lists or numpy arrays. A chunk with `embedding: None` stays keyword
  searchable. numpy scalars, `Path` and `datetime` values are stored as JSON.
- Writing the document and its chunks in two calls is fine. Search skips a chunk whose
  document is not there yet.

### C, API (Cyndia)

- Open `SqliteStore(INDEX_PATH)` once in the lifespan. It is safe across FastAPI's thread
  pool and no longer raises `NotImplementedError`, so the `FakeStore` fallback planned for
  C1 is no longer needed. There is a `close()`.
- `get_chunk` and `chunks_for_document` already return chunks without `embedding`, so C4
  has nothing to strip.
- `from engine.index.hybrid import Filters, hybrid_search`. Pass `query_vec=None` when
  embedding fails or `EMBED_FAKE=1`. Fake vectors only add noise to the ranking.
- The C3 confidence threshold of 0.03 in `api/prompts/answer.md` sits near the ceiling. The
  maximum score is 2/61 = 0.0328 (rank 1 in both lists). A cross-language answer tops out
  at 1/61 + 1/66 = 0.0315. BM25 only tops out at 1/61 = 0.0164, so in BM25-only mode no
  answer is ever "high". Pick the threshold per mode.
- Superseded chunks are still returned, demoted 5 ranks, with `status` and `superseded_by`
  set. For the prompt's "SUPERSEDED by X" label, read X's title with
  `store.get_document(superseded_by)`.
- `engine.index.hybrid` imports langdetect (already a dependency) and sets
  `DetectorFactory.seed = 0`, the same as A5.

### D, UI and demo (Lawrence)

- The superseded document stays in results below its replacement, with the badge. It is
  not removed.
- Demo Q1 (Malay question, English circular) needs live Cohere embeddings. There is no
  embedding fallback. With BM25 only, the English circular is not found.
- Demo Q3 search on the seed corpus with BM25 only ranks 02, 02, 10, 01 (superseded),
  01 (superseded). The 2024 circular is first and the badge shows at position 4.
- `docs/SYSTEM-DESIGN.md` "Index and search" does not yet mention the stopwords, the
  language-aware fusion, or auto-reload.

## Public API

```python
from engine.index.store import SqliteStore          # IndexStore implementation, plus close()
from engine.index.hybrid import Filters, hybrid_search, query_language
from engine.index.supersession import resolve_supersession

store = SqliteStore("data/index.sqlite")             # creates data/ if missing
results = hybrid_search(store, query, query_vec_or_None, Filters(department=...), top_k=10)
pairs = resolve_supersession(store)                  # [(old_doc_id, new_doc_id)]
```

```
uv run python eval/run.py --bm25-only     # no AWS
uv run python eval/run.py                 # embeds the questions with Cohere (A3)
```

## Tuning knobs

| Constant | File | Value | Meaning |
|---|---|---|---|
| `RRF_K` | hybrid.py | 60 | RRF damping |
| `SUPERSEDED_RANK_OFFSET` | hybrid.py | 5 | ranks a superseded chunk drops |
| `CROSS_LANGUAGE_OFFSET` | hybrid.py | 5 | imputed keyword rank = vector rank + this. A very large value behaves like plain RRF |
| `CANDIDATE_POOL` | hybrid.py | 200 | candidates per list without a filter |
| `SNIPPET_CHARS` | hybrid.py | 300 | snippet length |
| `MATCH_THRESHOLD` | supersession.py | 80 | rapidfuzz `partial_ratio` cut-off |
| `_STOPWORDS` | store.py | 83 words | Malay and English function words |

## Eval so far

Seed corpus: 15 PDFs, 26 chunks. The two scanned documents (05, 09) have no text layer and
no chunks until Textract lands.

- BM25 only: recall@5 = 5/10. All five misses ask in one language about a document
  written in the other (doc 08 is labelled mixed, but its text is Malay). The three
  same-language questions all hit at rank 1.
- Simulated vectors through the real `hybrid_search`, with the answer placed at vector rank
  1, 2, 3 or 5, averaged over 20 random orders of the other chunks:

| Answer's vector rank | recall@5, plain RRF | recall@5, language-aware | demo Qs in top 8, plain | demo Qs in top 8, language-aware |
|---|---|---|---|---|
| 1 | 0.70 | 1.00 | 1.00 | 1.00 |
| 2 | 0.70 | 1.00 | 1.00 | 1.00 |
| 3 | 0.70 | 1.00 | 0.88 | 1.00 |
| 5 | 0.66 | 0.88 | 0.70 | 1.00 |

  Same-language questions never lost first place. Simulated vectors are not Cohere: confirm
  at 2:30, and tune `CROSS_LANGUAGE_OFFSET` there.

## Known limitations

- The year guard blocks a same-year supersession (Bil. 3/2024 replacing Bil. 1/2024),
  because the plan says a candidate year equal to the newer year is skipped.
- Two- and three-word queries usually get no confident language, so they use plain RRF.
- Superseded demotion in BM25-only mode can put a loosely related document above the old
  circular (demo Q3: the budget minutes rank above it). The badge still shows.
