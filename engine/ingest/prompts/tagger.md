# Tagger prompt (task A4)

Model: `BEDROCK_TAG_MODEL` (Claude Haiku on Bedrock). Called once per document with the title
guess (filename) and the first 3 pages of text, capped at 6000 characters. Use structured
outputs (`output_config.format` with the JSON schema below) if the Bedrock model supports it,
otherwise parse the JSON and retry once on failure. `{{taxonomy}}` is the content of
`contracts/taxonomy.json`. `{{filename}}` and `{{text}}` are substituted at runtime.

## System

```
You classify Malaysian government agency documents. You read the start of a document and
return metadata as JSON. You only choose values from the taxonomy provided. If nothing fits,
use "other" for doc_type, "Umum" for department, and "lain" for topics. You never invent
reference numbers; you copy them exactly as they appear in the text.
```

## User

```
Taxonomy (choose only from these values):
{{taxonomy}}

Filename: {{filename}}

Document text (first pages):
<document>
{{text}}
</document>

Return a JSON object with exactly these keys:
- "title": the official title as printed, including any reference number such as
  "Pekeliling Perbendaharaan Bil. 3/2024" or "Circular No. 7/2023". If no title is printed,
  make a short descriptive one from the content.
- "doc_type": one value from taxonomy.doc_type.
- "department": the issuing department, one value from taxonomy.department. Map English
  names to the Malay taxonomy value (Finance -> "Jabatan Kewangan", HR -> "Jabatan Sumber
  Manusia", Procurement -> "Jabatan Perolehan", IT -> "Jabatan Teknologi Maklumat").
- "topics": 1 to 3 values from taxonomy.topic.
- "year": the year of issue as an integer, or null if not stated.
- "lang": "ms" if mostly Malay, "en" if mostly English, "mixed" if both appear substantially.
- "supersedes": a list of the exact reference numbers or titles of earlier documents that
  this document states it replaces, cancels, or supersedes. Look for phrases such as
  "menggantikan", "membatalkan", "supersedes", "replaces", "revokes", "cancels". Copy the
  reference exactly as written. Empty list if none.
- "summary": one sentence, in the document's own language, saying what the document is about.

Output only the JSON object.
```

## JSON schema for structured output

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["title", "doc_type", "department", "topics", "year", "lang", "supersedes", "summary"],
  "properties": {
    "title": {"type": "string"},
    "doc_type": {"type": "string"},
    "department": {"type": "string"},
    "topics": {"type": "array", "items": {"type": "string"}},
    "year": {"type": ["integer", "null"]},
    "lang": {"type": "string", "enum": ["ms", "en", "mixed"]},
    "supersedes": {"type": "array", "items": {"type": "string"}},
    "summary": {"type": "string"}
  }
}
```

## Validation after the call

1. If `doc_type`, `department`, or any `topics` value is not in the taxonomy, replace it with
   the fallback value and log a warning. Do not fail ingest over a bad tag.
2. If JSON parsing fails, retry once with the user message prefixed by
   "Your previous output was not valid JSON. Output only the JSON object." Then fall back
   to `doc_type="other"`, `department="Umum"`, `topics=["lain"]`, `supersedes=[]`,
   `title=filename`.
3. `summary` is stored on the document for the UI card. It is not indexed.

## Quick test set (run by eye on the seed corpus)

- A Malay circular that says "Pekeliling ini menggantikan Pekeliling Bil. 2/2022" must return
  `supersedes: ["Pekeliling Bil. 2/2022"]`.
- An English SOP from the IT department must return `department: "Jabatan Teknologi Maklumat"`.
- Meeting minutes must return `doc_type: "meeting_minutes"` and `topics` including `"mesyuarat"`.
