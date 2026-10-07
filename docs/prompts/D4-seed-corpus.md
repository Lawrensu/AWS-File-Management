# Seed corpus generation prompt (task D4)

Paste this into any capable LLM (Claude, DeepSeek, whatever has the most free quota). Run it
once. Save each document as `samples/src/NN-slug.md`. Then run `scripts/md_to_pdf.py`.

```
Generate 15 realistic but entirely fictional internal documents for a Sarawak state
government agency called "Jabatan Pembangunan Digital Sarawak". They will be used to test a
document search system. Do not reuse any real circular numbers, real names, or real policy
text. Invent plausible ones.

Output each document as a separate markdown file, starting with a YAML front matter block:

---
filename: 01-pekeliling-elaun-perjalanan-2024.md
doc_type: circular
department: Jabatan Kewangan
lang: ms
year: 2024
supersedes: ["Pekeliling Kewangan Bil. 2/2022"]
scanned: false
---

Then the document body, 400 to 900 words, formatted as the real document type would be:
circulars have a reference number, date, "Kepada:" line, numbered paragraphs, and a signature
block; SOPs have purpose, scope, numbered procedure steps, and a responsibility table;
meeting minutes have attendees, agenda items, decisions, and action items; guidelines have
sections and sub-sections.

Required mix (exactly):
- Languages: 6 in Bahasa Malaysia, 6 in English, 3 mixed (Malay headings and body with
  English technical terms, as is common in Malaysian agencies).
- Types: 5 circulars, 3 SOPs, 3 meeting minutes, 3 guidelines, 1 policy.
- Departments: use only these values: Jabatan Sumber Manusia, Jabatan Kewangan,
  Jabatan Perolehan, Jabatan Teknologi Maklumat, Jabatan Pentadbiran. Spread them out.
- Two supersession pairs: documents 01 and 02 are a 2022 circular and a 2024 circular on
  travel allowance rates where the 2024 one states in its body "Pekeliling ini menggantikan
  Pekeliling Kewangan Bil. 2/2022" and changes the per-kilometre rate from RM0.60 to RM0.70.
  Documents 03 and 04 are a 2021 and a 2023 English procurement circular where the 2023 one
  says "This circular supersedes Circular No. 5/2021" and raises the quotation threshold
  from RM20,000 to RM50,000.
- One document (an SOP) must describe a multi-step approval workflow for procurement above
  RM50,000 with named roles in order.
- One meeting minutes document must record a decision about a cybersecurity training
  deadline.
- Mark documents 05 and 09 with scanned: true (they will be rasterised later).

Include concrete, searchable facts in every document: rates, thresholds, deadlines, form
names, role titles. These are what test questions will target.

After the 15 documents, output a table "MANIFEST" with columns: filename, doc_type,
department, lang, year, supersedes, scanned, and a one-line "key fact" that a test question
could ask about.
```

## Converting to PDF

`scripts/md_to_pdf.py` (task D4, agent writes it): for each `samples/src/*.md`, render the
markdown to a PDF in `samples/` with fpdf2 (or `markdown` + `fpdf2`), one font that supports
Malay characters (DejaVu Sans is bundled with fpdf2). For files with `scanned: true`, open
the produced PDF with PyMuPDF, render each page to a PNG at 150 dpi, and build a new PDF
from the PNGs only, so there is no text layer. Save `samples/MANIFEST.md` from the table.
