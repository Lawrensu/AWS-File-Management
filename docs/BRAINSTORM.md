# Brainstorm: Intelligent Document Search for Government Agencies

Problem (from the hackathon brief): agencies hold thousands of policies, SOPs, circulars,
guidelines, reports and minutes. Finding the right one is slow. Build something that turns
that pile into an intelligent, searchable resource so staff find answers faster and decide better.

---

## 1. What the judges are actually scoring

Read the brief again: it says **find information faster** and **make better decisions**.
That is two products, not one:

| Need | What it means in practice | What a demo must show |
|---|---|---|
| Find faster | Search that understands meaning, not just keywords. Works on scanned PDFs. | Type a question in plain language, get the right document + the exact page in under 3 seconds. |
| Decide better | Answers, not links. With citations the user can verify. | "Can a contractor claim travel allowance?" returns a 3-line answer citing Circular 4/2023, para 7.2, with a link to the highlighted page. |

Everything we build should serve one of those two rows. If a feature does not, cut it.

**Context clue:** sponsors are SDEC (Sarawak Digital Economy Corporation). Real Sarawak
agency documents are in **Bahasa Malaysia and English, often mixed**. Multilingual retrieval
is not a nice-to-have, it is the thing that makes judges believe it would work in their office.

---

## 2. Review of our initial ideas

### 2.1 Central system vs client system
Keep the idea, sharpen the naming. In practice it is three pieces:

1. **Document Store** (the "central system"): the agency's documents. For us: an S3 bucket
   that plays the role of the agency's existing file share. Nothing clever lives here.
2. **Knowledge Engine**: the ingestion pipeline plus the index. This is the brains and the
   bulk of our work. It watches the store, processes every document, and keeps the index fresh.
3. **Client**: the search/chat UI that staff use. Thin. Talks to the engine over one API.

Why this split wins: we can say "point it at your existing file share, no migration" in the
pitch. Agencies do not want to move documents; they want to search what they already have.

### 2.2 Vision model / OCR for images inside documents
Yes, and go one step further. Two kinds of visual content:

- **Scanned text** (most government PDFs are scans of signed letters): use **Amazon Textract**.
  It is the AWS-native answer, handles tables and forms, and judges will recognise it.
- **Figures, org charts, flowcharts, stamped approvals**: OCR gives garbage. Send the image to
  a **multimodal LLM on Bedrock** and ask it to describe it in one paragraph. That description
  gets indexed like text. Demo moment: "find the approval workflow for procurement above RM50k"
  returns a flowchart that has no searchable text in it.

Decision rule per page: if Textract confidence is high and text density is normal, keep OCR
text. If a page has an embedded image larger than X% of the page, also run the vision
description. Keep both.

### 2.3 Algorithmic indexing (common words, rare words) before the LLM
This is a good instinct and it has a name: **BM25** (what Elasticsearch/OpenSearch use). It
already does exactly "rare words matter more, common words matter less" (inverse document
frequency). Do not reinvent it, use it, and add two things on top:

- **Keyword and entity extraction** per document (YAKE or KeyBERT, both run locally in
  milliseconds): pulls out the "rare but important" terms you described, like the name of a
  specific scheme or movement. Store them as metadata.
- **Dense embeddings** (Titan Text Embeddings v2 on Bedrock, multilingual) so "elaun
  perjalanan" and "travel allowance" land near each other.

Then **hybrid search**: run BM25 and vector search in parallel, merge with Reciprocal Rank
Fusion. This is the single biggest quality jump you can get and it is about 40 lines of code.

### 2.4 LLM-generated categorical tags
Yes, with one constraint that makes it actually useful: **a controlled vocabulary**. If the
LLM free-texts tags you get "HR", "Human Resources", "Sumber Manusia", "Staffing" for the same
thing and the tags become useless for filtering.

Instead, define a small taxonomy up front (document type, department, topic, year, status) and
make the LLM pick from it. Extracted keywords stay free-form; tags are closed-set. Tags then
power filters in the UI and a pre-filter before search (cheaper, faster, more precise).

Use the cheapest capable model on Bedrock for tagging (Claude Haiku class). It runs once per
document at ingest, not per query.

---

## 3. Differentiators (pick two, max three)

Ordered by demo impact divided by build cost.

1. **Cited answers with page highlight.** Answer plus "Source: Pekeliling 3/2024, page 4" and
   the PDF opens scrolled to that page with the passage highlighted. This is the "decide better"
   row and it is what makes judges trust the system. Build cost: medium (store page number and
   bounding box per chunk; Textract gives both).
2. **Bilingual by default.** Ask in Malay, get answers from English documents and vice versa.
   Build cost: near zero if we pick a multilingual embedding model and prompt the LLM to answer
   in the user's language.
3. **Supersession awareness.** Circulars replace older circulars. At ingest, the LLM extracts
   "this document supersedes X" and we mark X as outdated. Search results show a warning badge
   on outdated documents and prefer the current one. Judges who have worked in government will
   lean forward at this one. Build cost: low-medium (one extra extraction field, one flag).
4. **Access control by department** (Cognito groups, filter at query time). Real agencies
   need it. Build cost: medium. Mention in pitch, build only if time allows.
5. **Conflict detection** (two live documents disagree). Impressive, hard to demo reliably in
   a hackathon. Skip, mention as roadmap.

Recommendation: ship 1, 2, 3. Mention 4 and 5 as roadmap on the last slide.

---

## 4. Proposed architecture

```
                    DOCUMENT STORE (agency side)
                    S3 bucket  <-- upload via UI or drop files in
                          |
                          | S3 event / manual trigger
                          v
   +--------------------- KNOWLEDGE ENGINE ---------------------+
   |                                                            |
   |  Ingest worker (Python)                                    |
   |   1. Detect type (PDF text / PDF scan / image / DOCX)      |
   |   2. Extract text: Textract (scans), pypdf (native)        |
   |   3. Describe images: Bedrock multimodal                   |
   |   4. Chunk by page + heading (keep page no. + bbox)        |
   |   5. Keywords: YAKE  |  Tags + supersedes: Bedrock Haiku   |
   |   6. Embed chunks: Titan Embeddings v2                     |
   |   7. Write to index                                        |
   |                                                            |
   |  Index store (one of):                                     |
   |   A. OpenSearch Serverless  (BM25 + kNN in one query)      |
   |   B. Postgres + pgvector + tsvector  (cheap, one container)|
   |                                                            |
   |  Query API (FastAPI)                                       |
   |   /search   hybrid BM25 + vector, RRF merge, tag filters   |
   |   /ask      search -> top-k chunks -> Bedrock Claude ->    |
   |             answer + citations (doc, page, bbox)           |
   |   /documents, /documents/{id}/pages/{n}  (viewer support)  |
   +------------------------------------------------------------+
                          |
                          v
                    CLIENT (Next.js)
                    Search box + filters | Chat with citations
                    PDF viewer with highlighted passage
```

### Index store decision
- **OpenSearch Serverless**: native hybrid search, very AWS, but minimum cost is around
  USD 170 per month even idle (0.5 OCU dev mode). Fine if the hackathon gives credits.
- **Postgres + pgvector**: free on a laptop, runs in one Docker container, deploys to RDS or
  a tiny EC2 later. BM25-ish via `tsvector`, vectors via pgvector. Slightly more code.

Recommendation: **pgvector** unless credits are confirmed generous. The AI parts (Textract,
Bedrock embeddings, Bedrock Claude) are already clearly AWS; the index store is plumbing.
Abstract it behind one `IndexStore` interface so it can be swapped if we get credits.

### Chunking
Chunk per page first, then split long pages at headings or 800 tokens with 100 overlap.
Every chunk carries `{doc_id, page, bbox, heading_path, lang}`. Page is mandatory; it is what
makes citations work.

### Cost control
- Tagging and image description run once per document at ingest, with the cheapest model.
- Embeddings are cached by content hash so re-ingesting an unchanged file costs nothing.
- Answer generation uses a mid-tier model, streaming, with top-k capped at 8 chunks.

---

## 5. Scope by phase

**Phase 0 (first 2 hours): contracts.** Agree the JSON shapes for Document, Chunk, Tag,
SearchResult, Answer and the API routes. Everyone builds against mocks of these. This is what
lets four people work in parallel without blocking each other.

**Phase 1: vertical slice.** One native-text PDF goes in, one question comes out with a cited
answer, shown in a basic UI. No OCR, no tags, no polish. Target: end of day 1 or earlier.

**Phase 2: the real thing.** Textract for scans, vision for figures, tags, hybrid search,
supersession, bilingual. PDF viewer with highlights.

**Phase 3: demo and pitch.** Seed 30 to 50 realistic documents (mix of Malay and English,
some scanned), rehearse three scripted questions, build the slide deck, record a backup video.

---

## 6. Name ideas

- **Rujuk** (Malay: "to refer / consult"). Short, local, and exactly what the tool does.
- **Arkib Pintar** (Smart Archive).
- **DocuGov** / **GovBrain** (safe, generic).

---

## 7. Decisions (confirmed)

1. Team of 4. Workstreams A, B, C, D in `docs/PLAN.md`.
2. **4 hours remaining.** Plan is cut to fit; see `docs/PLAN.md` for the checkpoints.
3. Index store: pgvector was picked, but with 4 hours we start in-process (SQLite + BM25 +
   numpy) behind the `IndexStore` interface. pgvector is a stretch swap.
4. Stack: Python FastAPI + Next.js. PyMuPDF for all PDF handling.
5. All four differentiators. Access control is shipped as department scoping in the UI,
   presented as "Cognito-ready". Vision description of figures (section 2.2) is cut.
