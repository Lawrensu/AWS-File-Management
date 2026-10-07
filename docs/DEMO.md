# Rujuk live demo

Script for the 3 to 4 minute live demo. The presenter and whoever records the backup read this.

## Setup before the demo

- Run `uv run python -m engine.ingest samples/`
- Run `uv run uvicorn api.main:app --reload`
- In a second terminal, run `pnpm --dir web dev`
- Make sure `web/.env.local` does not set `NEXT_PUBLIC_USE_MOCK=1`
- Open http://localhost:3000
- Set the department selector to Umum
- Set browser zoom to 125 percent

## Q1 Bilingual

- Page: Ask
- Type: Berapakah had pembelian terus untuk perolehan?
- Expected answer: RM50,000, effective 1 June 2023
- Expected source: `04-circular-procurement-quotation-2023.pdf`, an English circular
- Presenter says: I asked in Malay, and it answered from an English circular, in Malay.

## Q2 Citation and highlight

- Page: Ask
- Type: How many days of annual leave do staff get after 10 years of service?
- Expected answer: 25 days
- Expected source: `13-guideline-leave-application-2024.pdf`
- Click the citation chip. The page opens with the passage highlighted.
- Presenter says: Every claim has a source, and one click shows the exact passage.

## Q3 Supersession

- Page: Search
- Type: kadar tuntutan perbatuan kereta
- Expected: the 2024 circular ranks first, and the 2022 circular shows a red Superseded badge
- Then switch to Ask and type: What is the current car mileage claim rate?
- Expected answer: RM0.70 per km from `02-pekeliling-elaun-perjalanan-2024.pdf`, noting that the 2022 rate of RM0.60 was superseded
- Presenter says: Old circulars stay findable, but staff are never given an outdated rate.

## Fallback if something breaks

- Set `NEXT_PUBLIC_USE_MOCK=1` in `web/.env.local` and restart `pnpm --dir web dev`
- Or play the backup recording

## Talking points

- Find faster: search understands meaning, not only keywords.
- Decide better: every answer is cited, and one click opens the highlighted page.
- Bilingual: ask in Malay or English, and get answers from documents in either language.
- Supersession: replaced circulars are flagged, so nobody acts on an old rule.
- Department scoping: each view is filtered by department, ready for Cognito sign-in.
- AWS: Amazon Bedrock with Titan Text Embeddings v2 for search, Claude Haiku for tagging, and Claude Sonnet for answers.
- Say Textract only if scanned-page OCR landed. Say S3 only if uploads write to S3.

## Recording checklist

- Record all three questions end to end on the real API, not mock mode
- Take three screenshots during the run: search with the Superseded badge, a cited answer, and the highlighted viewer
- Save the screenshots as `docs/screenshots/search.png`, `docs/screenshots/ask.png`, and `docs/screenshots/viewer.png`
- Upload the video as an unlisted YouTube or Google Drive link, not into the repo
- Put the video link in the README submission checklist
