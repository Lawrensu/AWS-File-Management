# Workstream B review: index and retrieval

Author: Noah (B). Date: 2026-10-07. Status: **open for team review.**

This is a review of the B tasks in `docs/PLAN.md` (B1 to B5), their prompts in
`docs/AGENT-PROMPTS.md`, and the `IndexStore` interface in `engine/index/store.py`, done
before any B code was written. Nothing here is implemented yet. `PLAN.md` and
`AGENT-PROMPTS.md` stay unchanged until the team agrees, then they get updated in one commit.

Findings 1 to 6 were measured with the real libraries (rank-bm25 0.2.2, rapidfuzz 3.14.6,
numpy 2.5.3, Python sqlite3). The script and its output are at the bottom so anyone can rerun
them.

None of the proposed fixes changes `contracts/` or the `IndexStore` method signatures.
Finding 1 changes ranking behaviour that the plan describes, so it needs a team decision.

## Summary

| # | Finding | Severity | Task | Affects |
|---|---|---|---|---|
| 1 | Superseded penalty `score * 0.3` sends old docs to last place | High: breaks demo Q3 | B2 | C3, D2, D7 |
| 2 | rank_bm25 gives zero or negative scores on tiny corpora, crashes on empty | High: 1:30 slice | B1 | C1, slice |
| 3 | Fuzzy supersession matching marks the wrong circulars superseded | High: wrong badges | B3 | C3, D2 |
| 4 | SQLite connection crashes under FastAPI's thread pool | High | B1 | C1 to C5 |
| 5 | API never sees documents ingested by the CLI | Medium | B1 | A6, demo |
| 6 | `data/` does not exist on a fresh clone | Medium | B1 | C1 |
| 7 | Candidate pool too small for filters; "Umum" docs hidden by department filter | Medium | B2 | D6 |
| 8 | No fallback when the query embedding fails | Medium | B2 | C2, C3 |
| 9 | Store would hand out its cached dicts | Low | B1 | B3, C4 |
| 10 | `IndexStore` has two abstract methods the B1 row does not list | Low | B1 | none |
| 11 | B2 and B3 do not actually depend on B1 | Schedule | B2, B3 | C2 |
| 12 | Eval matches on tagger titles and needs AWS | Low | B4 | none |
| 13 | Branch rules disagree between README and AGENTS.md | Process | none | everyone |

---

## 1. Superseded penalty buries old documents (B2)

**Spec.** PLAN B2 and the B2 prompt: multiply the score by 0.3 when the document is
superseded and `include_superseded` is false, "instead of removal so the badge can still
show".

**Evidence.** RRF scores with k=60 sit in a narrow band. A chunk at rank r in one list scores
`1/(60+r)`: rank 1 is 0.0164, rank 30 is 0.0111. A superseded chunk ranked 1st in both lists
scores `2/61 = 0.0328`, and `* 0.3` gives 0.0098. That is below the lowest score any
candidate in the 30-per-list pool can have (0.0111), so the superseded chunk always ranks
last, whatever its raw rank. Measured with BM25 and vector rankings in agreement, 30
candidates:

| Demotion | Old circular raw #2 lands at | New circular |
|---|---|---|
| `* 0.3` (spec) | 30th of 30 | 1st |
| `* 0.7` | 28th | 1st |
| `* 0.9` | 8th | 1st |
| rank + 5 (proposed) | 6th | 1st |

**Consequence.** With top 10 on `/search` and top 8 on `/ask`, the superseded circular never
appears. D7 demo Q3 ("shows the badge plus the newer answer") cannot work, and the C3 trick
question ("What is the travel allowance rate?" must cite the current circular and mention
the old one is superseded) cannot pass, because the answer prompt never receives the old
excerpt. No multiplier is safe: anything below about 0.67 drops below every candidate that
appears in both lists.

**Proposed fix.** Demote by rank, not by score. When fusing, score a superseded chunk as if
it sat `SUPERSEDED_RANK_OFFSET = 5` places lower in each list: `1/(60 + rank + 5)`. The
demotion is bounded to a few places, the current version always outranks an equally ranked
superseded one, and `include_superseded=True` removes the offset. Extra test: a superseded
chunk ranked 1st in both lists, with 28 other candidates, stays inside top 10 and below the
current chunk.

## 2. rank_bm25 on tiny and empty corpora (B1)

**Spec.** B1 builds `rank_bm25.BM25Okapi` over all chunks when the store opens.

**Evidence.** BM25Okapi uses `idf = log(N - n + 0.5) - log(n + 0.5)` and floors negative
values at `epsilon * average_idf`, which is itself negative when most terms are. Query
"elaun":

| Corpus | Scores |
|---|---|
| 1 chunk containing "elaun" | `[-0.275]` |
| 2 chunks, "elaun" in the first | `[0.0, 0.0]` |
| 3 chunks, "elaun" in the first | `[0.511, 0.0, 0.0]` |
| empty | `ZeroDivisionError` in the constructor |

**Consequence.** At the 1:30 slice (one PDF, a few chunks) BM25 returns nothing useful. C1
opens the store at startup against an empty index, so building BM25 eagerly crashes the API
before anything is ingested. If zero-score chunks are returned they enter RRF at arbitrary
ranks and add noise.

**Proposed fix.**
- Return `[]` without building BM25 when there are no chunks.
- Subclass `BM25Okapi` and override `_calc_idf` with the Lucene formula
  `log(1 + (N - n + 0.5) / (n + 0.5))`, which is always positive. Verified: the 1, 2 and 3
  chunk cases above score `[0.288]`, `[0.693, 0.0]` and `[0.981, 0.0, 0.0]`.
- `bm25_search` drops results with score <= 0.

`_calc_idf` is private, but 0.2.2 is still the latest rank-bm25 release, so the override is
stable.

## 3. Fuzzy supersession matching hits the wrong circular (B3)

**Spec.** The B3 prompt picks the best match by `fuzz.partial_ratio(reference, title)` and
accepts it at >= 80.

**Evidence.** Circulars in the same series differ only in their number, and partial_ratio
barely notices:

| Score | Reference | Title |
|---|---|---|
| 100.0 | Pekeliling Kewangan Bil. 2/2022 | Pekeliling Kewangan Bil. 2/2022 Kadar Elaun |
| 95.1 | Pekeliling Kewangan Bil. 2/2022 | Pekeliling Kewangan Bil. 3/2024 |
| 95.1 | Pekeliling Kewangan Bil. 2/2022 | Pekeliling Kewangan Bil. 1/2023 Had Tuntutan |
| 100.0 | Circular No. 5/2021 | Procurement Circular No. 5/2021: Quotation Thresholds |
| 89.5 | Circular No. 5/2021 | Procurement Circular No. 7/2023 |

**Consequence.** If the referenced circular is not in the corpus, or the tagger titled it
differently, the reference matches another circular in the same series and marks it
superseded. The year guard only blocks matches with a later or equal year. Example: a 2024
circular says it replaces Bil. 2/2022, which is not indexed, and Bil. 1/2023 is. It scores
95.1, 2023 is earlier than 2024, so Bil. 1/2023 gets a wrong "Superseded" badge and is
demoted.

**Proposed fix.** Pull reference numbers out of the reference with a regex like
`(\d+)\s*/\s*(\d{4})`. If the reference has one, a candidate qualifies only if its title or
filename contains the same number. partial_ratio then ranks the qualifying candidates. If
the reference has no number, keep the fuzzy rule as specified. Extra test: a reference to
Bil. 2/2022 with only Bil. 1/2023 indexed marks nothing.

Also: `resolve_supersession` must be idempotent, because it runs after every ingest and every
upload. A re-ingested old document comes back from A6 with `status="current"` until resolve
runs again, which is fine as long as A6 and C5 always call it.

## 4. SQLite connection and FastAPI threads (B1)

FastAPI runs plain `def` routes in a thread pool, and the store is opened in the lifespan on
a different thread. By default Python's sqlite3 refuses that:

```
ProgrammingError: SQLite objects created in a thread can only be used in that same thread.
```

**Proposed fix.** `sqlite3.connect(path, check_same_thread=False, timeout=30)`, plus a
`threading.RLock` around writes and in-memory index rebuilds. C5 upload writes while
searches read.

## 5. API does not see documents ingested by the CLI (B1)

`uv run python -m engine.ingest samples/` (A6) is a separate process. SqliteStore loads
everything into memory when it opens, so a running API keeps serving the old index until it
is restarted.

**Proposed fix.** Before each read, run `PRAGMA data_version`. Its value changes whenever
another connection commits, including one in another process (verified: 1 then 2). Reload
when it changes. That costs one tiny query per search. Also set `PRAGMA journal_mode=WAL` so
the CLI writing and the API reading do not hit "database is locked". If the team prefers no
magic, the fallback is a line in `docs/DEMO.md`: restart uvicorn after a CLI ingest.

## 6. `data/` does not exist on a fresh clone (B1)

`INDEX_PATH` defaults to `data/index.sqlite`, and `data/` is gitignored. `sqlite3.connect`
raises `OperationalError: unable to open database file` when the folder is missing.

**Proposed fix.** `Path(path).parent.mkdir(parents=True, exist_ok=True)` before connecting,
skipped for `:memory:`.

## 7. Filters: pool size and "Umum" (B2)

**Pool size.** B2 fetches `top_k * 3` (30) chunks from each search, then filters. With a
department selected, that department's chunks may not be among those 30, so results come
back short or empty, which is exactly what D6 demos. The corpus is small (15 documents) and
both searches already score every chunk, so a wider pool is free. **Proposed fix:** fetch at
least 200 candidates per list, or every chunk when a filter is set.

**"Umum".** The spec keeps a document only if its department equals the selected one. The
A4 tagger falls back to "Umum" (general) when it cannot tell the department, so those
documents disappear from every department view. **Proposed fix:** with a department
selected, keep documents whose department equals it **or** is "Umum". Selecting "Umum" or
nothing still means no filter, as `contracts/api.md` says.

## 8. No fallback when the query embedding fails (B2)

If Bedrock is throttled, credentials expire, or the demo wifi drops, C2 and C3 cannot embed
the query and search fails completely.

**Proposed fix.** `hybrid_search` takes `query_vec: np.ndarray | None`. With `None` it runs
BM25 only. C2 and C3 catch embedding errors and pass `None`. This is B's own function, not
`IndexStore`, so no interface change.

## 9. Store must not hand out its cached dicts (B1)

If `get_document`, `list_documents` or `get_chunk` return the dicts the store caches, a
caller that mutates them (C4 popping `embedding`, B3 setting `status` before upserting)
silently changes the in-memory index.

**Proposed fix.** Return copies. `get_chunk` and `chunks_for_document` return chunks without
`embedding` (it is optional in the schema and the API never returns it). On load, normalise
vectors instead of assuming Titan returned unit vectors, skip chunks whose embedding is
null, and raise a clear error on a dimension mismatch instead of hardcoding 1024.

## 10. Two abstract methods missing from the B1 row

`engine/index/store.py` declares `chunks_for_document` and `count` as abstract. The B1 row in
`PLAN.md` does not list them, but `SqliteStore` cannot be instantiated without them, and C4
(`chunks_for_document`) and `/health` (`count`) use them. B1 will implement them. The B1 row
should name them.

## 11. Schedule: B2 and B3 can start at 0:15

`PLAN.md` marks B2 and B3 "[A] after B1" and the dependency graph puts them at 1:00. But
their prompts test against a fake in-memory `IndexStore` and say not to depend on
`SqliteStore`, so they only need `store.py`, which already exists. **Proposed:** start both
agents at 0:15 alongside B1. C2 needs B2 for the 1:30 slice, and this gives about 45 minutes
of slack.

B1 is on the critical path (A6 needs it at 0:45, C1's lifespan opens it), so B1 gets pushed
as soon as it works, before any polish.

## 12. Eval runner (B4)

B4 counts a hit when a result title contains `expected_doc_title_contains`. Titles come from
the A4 tagger and can change between runs.

**Proposed fix.**
- `eval/questions.json` keys questions by `expected_filename` (deterministic, from
  `samples/MANIFEST.md`). The title field stays as a fallback.
- Add a `--bm25-only` flag so eval runs without Bedrock credentials.
- Write the 10 questions from the MANIFEST "key fact" column. Include Malay questions aimed
  at English documents and the reverse. BM25 cannot match across languages, so those
  questions are the test of Titan v2's Malay.

## 13. Branch rules disagree

`README.md` says branch from `dev-law` and PR to `dev-law`. `AGENTS.md` says branches are
`<name>/<workstream><task>` and PRs go to `main`. The remote also has `dev-<name>` branches
that match neither. **Proposed:** the team confirms the integration branch, and the other
file gets updated to match.

## B5: recommend dropping it

`PgVectorStore` plus docker compose is 60 minutes and changes nothing in the demo. That time
is better spent at 2:30 running eval on the seed corpus and tuning the rank offset, pool
size, and tokenizer.

---

## Asks for each person

- **Malissa (A6):** call `resolve_supersession(store)` once at the end of the ingest CLI,
  after all files. The B3 row says "run at end of ingest", but the A6 row does not mention
  it.
- **Cyndia (C1 to C3):** import with `from engine.index.hybrid import Filters,
  hybrid_search`. Pass `query_vec=None` when embedding fails (finding 8). Finding 1 decides
  whether your superseded trick question can pass.
- **Lawrence (D2, D6, D7):** findings 1 (badge visibility in demo Q3) and 7 ("Umum" docs in
  department views).
- **Everyone:** finding 13.

## Decisions requested

Tick or comment in the PR or the group chat.

- [ ] F1: replace `score * 0.3` with a rank offset of 5 for superseded chunks
- [ ] F3: require the reference number to match before fuzzy matching
- [ ] F5: auto-reload via `PRAGMA data_version` (or document "restart uvicorn")
- [ ] F7: candidate pool of 200, and "Umum" documents visible under every department
- [ ] F8: `query_vec=None` means BM25-only
- [ ] F11: start B2 and B3 at 0:15
- [ ] F12: eval questions keyed by filename
- [ ] F13: which branch is the integration branch
- [ ] Drop B5

---

## Reproduce

Run from the repo root after `uv sync --extra dev`: save the script as a file, then
`uv run python <file>`. It uses only project dependencies and the standard library.

```python
import os
import sqlite3
import tempfile
import threading

from rank_bm25 import BM25Okapi
from rapidfuzz import fuzz

# F1: superseded demotion under RRF (k=60). BM25 and vector rankings agree,
# current circular NEW is raw #1, superseded OLD is raw #2, 30 candidates.
K = 60
ranked = ["NEW", "OLD"] + [f"c{i}" for i in range(28)]
for label, factor, offset in [("x0.3 (spec)", 0.3, 0), ("x0.7", 0.7, 0), ("x0.9", 0.9, 0),
                              ("rank + 5", 1.0, 5)]:
    scores = {}
    for rank, cid in enumerate(ranked, 1):
        old = cid == "OLD"
        scores[cid] = 2 / (K + rank + (offset if old else 0)) * (factor if old else 1)
    order = sorted(scores, key=scores.get, reverse=True)
    print(f"F1 {label:12} OLD at {order.index('OLD') + 1:2} of {len(order)}, "
          f"NEW at {order.index('NEW') + 1}")

# F2: rank_bm25 on tiny and empty corpora
for corpus in ([["kadar", "elaun"]],
               [["kadar", "elaun"], ["cuti", "rehat"]],
               [["kadar", "elaun"], ["kadar", "cuti"], ["kadar", "latihan"]]):
    scores = [round(float(s), 3) for s in BM25Okapi(corpus).get_scores(["elaun"])]
    print(f"F2 {len(corpus)} chunk(s), query 'elaun': {scores}")
try:
    BM25Okapi([])
except ZeroDivisionError as e:
    print(f"F2 empty corpus: ZeroDivisionError: {e}")

# F3: fuzzy supersession matching, threshold 80
for ref, title in [
    ("Pekeliling Kewangan Bil. 2/2022", "Pekeliling Kewangan Bil. 2/2022 Kadar Elaun"),
    ("Pekeliling Kewangan Bil. 2/2022", "Pekeliling Kewangan Bil. 3/2024"),
    ("Pekeliling Kewangan Bil. 2/2022", "Pekeliling Kewangan Bil. 1/2023 Had Tuntutan"),
    ("Circular No. 5/2021", "Procurement Circular No. 5/2021: Quotation Thresholds"),
    ("Circular No. 5/2021", "Procurement Circular No. 7/2023"),
]:
    print(f"F3 {fuzz.partial_ratio(ref, title):5.1f}  {ref!r} vs {title!r}")

# F4: sqlite3 connection opened on one thread, used on another (FastAPI thread pool)
con = sqlite3.connect(":memory:")
out = []


def use():
    try:
        con.execute("select 1")
        out.append("ok")
    except sqlite3.ProgrammingError as e:
        out.append(f"ProgrammingError: {e}")


t = threading.Thread(target=use)
t.start()
t.join()
print(f"F4 {out[0]}")

# F5: PRAGMA data_version sees commits made by another connection (another process works too)
path = os.path.join(tempfile.mkdtemp(), "index.sqlite")
api, cli = sqlite3.connect(path), sqlite3.connect(path)
cli.execute("create table t (x)")
cli.commit()
before = api.execute("pragma data_version").fetchone()[0]
cli.execute("insert into t values (1)")
cli.commit()
after = api.execute("pragma data_version").fetchone()[0]
print(f"F5 data_version before={before} after={after} changed={before != after}")

# F6: INDEX_PATH under a directory that does not exist yet (data/ is gitignored)
try:
    sqlite3.connect(os.path.join(tempfile.mkdtemp(), "data", "index.sqlite"))
except sqlite3.OperationalError as e:
    print(f"F6 OperationalError: {e}")
```

Output (Python 3.12, rank-bm25 0.2.2, rapidfuzz 3.14.6):

```
F1 x0.3 (spec)  OLD at 30 of 30, NEW at 1
F1 x0.7         OLD at 28 of 30, NEW at 1
F1 x0.9         OLD at  8 of 30, NEW at 1
F1 rank + 5     OLD at  6 of 30, NEW at 1
F2 1 chunk(s), query 'elaun': [-0.275]
F2 2 chunk(s), query 'elaun': [0.0, 0.0]
F2 3 chunk(s), query 'elaun': [0.511, 0.0, 0.0]
F2 empty corpus: ZeroDivisionError: division by zero
F3 100.0  'Pekeliling Kewangan Bil. 2/2022' vs 'Pekeliling Kewangan Bil. 2/2022 Kadar Elaun'
F3  95.1  'Pekeliling Kewangan Bil. 2/2022' vs 'Pekeliling Kewangan Bil. 3/2024'
F3  95.1  'Pekeliling Kewangan Bil. 2/2022' vs 'Pekeliling Kewangan Bil. 1/2023 Had Tuntutan'
F3 100.0  'Circular No. 5/2021' vs 'Procurement Circular No. 5/2021: Quotation Thresholds'
F3  89.5  'Circular No. 5/2021' vs 'Procurement Circular No. 7/2023'
F4 ProgrammingError: SQLite objects created in a thread can only be used in that same thread. ...
F5 data_version before=1 after=2 changed=True
F6 OperationalError: unable to open database file
```

## Setup note

Windows on ARM64 works: numpy 2.5.3, rapidfuzz 3.14.6 and pymupdf 1.28.2 publish `win_arm64`
wheels, and rank-bm25 is pure Python.
