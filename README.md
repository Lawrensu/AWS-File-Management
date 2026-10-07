# Rujuk

Document search and Q&A for government agencies. AWS hackathon, 4-hour build.

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

## Requirements

Install these if missing.

- Git
- Python 3.11 or newer: https://www.python.org/downloads/
- uv: `pip install uv` or https://docs.astral.sh/uv/getting-started/installation/
- Node.js 20 or newer: https://nodejs.org/
- pnpm: `npm install -g pnpm`
- AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
- An AWS account with Bedrock model access enabled in your region for
  `amazon.titan-embed-text-v2:0` and the Claude models listed in `.env.example`.
  Textract is only needed for the scanned-document stretch.

Python dependencies are in `pyproject.toml` and installed by `uv sync`. Web dependencies are
in `web/package.json` and installed by `pnpm install`.

## Run it

```bash
uv sync --extra dev
cp .env.example .env            # fill in AWS_PROFILE and AWS_REGION
uv run python -m engine.ingest samples/
uv run uvicorn api.main:app --reload
```

In a second terminal:

```bash
cd web && pnpm install && pnpm dev
```

Open http://localhost:3000. Without AWS credentials, set `EMBED_FAKE=1` before the ingest
and API commands; search still works on keywords, `/ask` does not.

## Submission checklist

- Repository is public
- README lists all group members
- README has 2 to 3 screenshots
- `docs/DEMO.md` has the three demo questions and the backup recording link

## Start here (team)

1. Get the code and your branch.

   ```bash
   git fetch origin
   git checkout dev-<yourname>
   git merge origin/dev-law
   ```

2. Open `docs/PLAN.md`. Find your name. "Who blocks whom" tells you what to push first.
   "Order of work" tells you what to do at each clock mark.

3. Read `AGENTS.md`. Then only the files in `contracts/` your tasks mention.

4. Set up.

   ```bash
   uv sync --extra dev
   cp .env.example .env
   aws sts get-caller-identity
   ```

   Fill in `.env`. Check Bedrock model access in the console for the region. If a model is
   missing, say so in the chat now. No credentials yet? `EMBED_FAKE=1` runs everything
   without AWS.

5. Kick off your agent. Open it in the repo root and paste, with your name and letter:

   ```
   I am <name>, owner of workstream <letter> in docs/PLAN.md. Read AGENTS.md,
   contracts/README.md, and my section of docs/PLAN.md. Tell me which of my tasks are [A]
   and can start now, which [H] task I do first, and whether `uv sync --extra dev` and
   `aws sts get-caller-identity` pass on this machine. Do not write code yet.
   ```

   For each [A] task it names, open a fresh agent session and paste that task's block from
   `docs/AGENT-PROMPTS.md`. One task per session. Keep your main session for your [H] task.

6. Commit small, push often, merge to `dev-law` when a task is done. If your task is one of
   the three gates in the plan, push the moment it works and say so in the chat.

## Rules that bite

- Do not edit another workstream's package. Stub it with `TODO(<letter>)`.
- Every chunk has a page number.
- Tell the group before changing anything in `contracts/`.
- Blocked more than 10 minutes? Say so in the chat.

## Checkpoints

- 1:30 One PDF in, one cited answer out, shown in the UI. Protect this over any feature.
- 3:00 Feature freeze.
- 3:30 Demo rehearsed twice, backup recording made.
- 4:00 Submitted.
