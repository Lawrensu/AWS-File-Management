# Rujuk

Rujuk is document search and Q&A for government agencies, built for an AWS hackathon in 4 hours. It ingests PDFs, including scans, and indexes them with hybrid keyword and vector search. Staff ask in Malay or English and get cited answers with the source page highlighted.

## Team

- Lawrence: Prepped the repo, UI, seed corpus, demo
- Malissa: ingest pipeline
- Noah: index and retrieval
- Cyndia: API and answer generation

## Screenshots

<!-- Replace before submission. Keep 2 to 3. -->

- `docs/screenshots/search.png`: search results with tags and the Superseded badge
- `docs/screenshots/ask.png`: a cited answer in Malay from an English document
- `docs/screenshots/viewer.png`: the page viewer with the cited passage highlighted

## Documentation

- [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md): read first to install, configure, run, and test.
- [docs/SYSTEM-DESIGN.md](docs/SYSTEM-DESIGN.md): read to understand the problem, architecture, and key decisions.
- [docs/PLAN.md](docs/PLAN.md): read to see who owns which task and the order of work.
- [docs/AGENT-PROMPTS.md](docs/AGENT-PROMPTS.md): read when you hand a task to a coding agent.
- [contracts/README.md](contracts/README.md): read before touching any shared data shape or API route.
- [AGENTS.md](AGENTS.md): read for repo rules, layout, stack, and the docs writing convention.

## Submission checklist

- Repository is public
- README lists all group members
- README has 2 to 3 screenshots
- `docs/DEMO.md` has the three demo questions and the backup recording link
