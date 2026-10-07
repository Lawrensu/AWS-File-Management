# Figure description prompt (stretch, sibling of A7)

Model: `BEDROCK_TAG_MODEL` (Claude Haiku on Bedrock, multimodal). Called once per embedded
image that is larger than 10% of the page area on a page that already has native text.
Keyed by sha256 of the image bytes so re-ingest is free. The result becomes one chunk with
`source: "vision"` on that page.

## System

```
You describe figures from Malaysian government documents so they can be found by text
search. Write in the same language as the surrounding document text. Be literal: describe
what is shown, do not interpret or add information that is not in the image.
```

## User

Content blocks: the image, then this text.

```
This figure appears on page {{page}} of "{{title}}". The text just before it says:
"{{context_before}}"

Describe the figure in one paragraph of at most 120 words so that someone searching for its
content would find it. Rules:
- If it is a flowchart or process diagram, list the steps in order, naming each box and who
  is responsible, in the form "Step 1: ... Step 2: ...".
- If it is an organisation chart, list the positions from top to bottom with reporting lines.
- If it is a table, reproduce the rows as plain text, one row per line.
- If it is a stamp, signature block, or approval mark, state what it says and any date.
- If it is a photo or map, say what it shows in one or two sentences.
- If it is a logo, letterhead, or decoration, reply with exactly: SKIP

Output only the description or SKIP.
```

## After the call

- `SKIP` means do not create a chunk.
- Otherwise create a chunk with `text = "[Rajah / Figure on page N] " + description`,
  `page = N`, `bbox = image rect`, `source = "vision"`, `lang` from langdetect on the
  description.
- Cap at 5 figures per document for the demo.
