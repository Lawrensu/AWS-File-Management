# Getting started

This doc gets Rujuk running on your machine. Read it if you are a teammate or a judge who wants to run it.

## Requirements

- Git.
- Python 3.11 or newer: https://www.python.org/downloads/
- uv: `pip install uv` or https://docs.astral.sh/uv/getting-started/installation/
- Node.js 20 or newer: https://nodejs.org/
- pnpm: `npm install -g pnpm`
- AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
- An AWS account with Bedrock model access in your region.
- Textract is only needed for the scanned-document stretch.

## Install

```bash
uv sync --extra dev
pnpm --dir web install
```

## Configure

- Copy the example file and edit it. `.env` is gitignored.

```bash
cp .env.example .env
```

- Set `AWS_PROFILE` and `AWS_REGION`. The default region is `ap-southeast-1`.
- Model IDs are `BEDROCK_EMBED_MODEL`, `BEDROCK_TAG_MODEL` and `BEDROCK_ANSWER_MODEL`.
- Embeddings use Cohere Embed Multilingual v3 (`cohere.embed-multilingual-v3`) in `ap-southeast-1`. Enable model access for it in the Bedrock console.
- Claude model IDs are pending a retest after AWS account verification.
- Check Bedrock model access in the console for your region. If a model is only on a cross-region inference profile, put that ID in `.env`.
- Confirm your credentials work.
```bash
aws sts get-caller-identity
```

- Only Lawrence's machine has model access, AWS and Groq. The integrated demo and every real end to end test run there.
- Everyone else sets `EMBED_FAKE=1`, leaves `GROQ_API_KEY` empty, and tests with `engine.llm` and `embed_texts` stubbed. `engine.llm` raises `LLMUnavailable` on those machines, which is expected. Do not try to fix provider, credential or network errors.
- Write Bedrock calls to read model IDs and region from `.env`. Never hardcode them.
- `GROQ_API_KEY` turns on the free Groq fallback for tagging and answers. Only Lawrence's machine has one. Leave it empty elsewhere.
- `BEDROCK_CLIENT` (`mantle` by default, or `converse`) and `LLM_BEDROCK_COOLDOWN` (seconds, default 300) tune `engine/llm.py`.
- Groq has no embeddings. If Bedrock is down, search runs on BM25 only.
- `S3_BUCKET` is optional. Leave it empty to keep uploads in `data/uploads/`.
- `INDEX_PATH` defaults to `data/index.sqlite`.
- `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000`.
- `EMBED_FAKE=1` skips Bedrock embeddings.
  - Set it before the ingest and API commands.
  - Search still works on keywords.
  - `/ask` does not work.

## Run

- Ingest the sample corpus, then start the API.

```bash
uv run python -m engine.ingest samples/
uv run uvicorn api.main:app --reload
```

- In a second terminal, start the web app.

```bash
pnpm --dir web dev
```

- Open http://localhost:3000.
- Mock mode runs the search page without the API.
  - Set `NEXT_PUBLIC_USE_MOCK=1`. It reads `web/mock/search.json`.

## Test

- Python tests use `FakeStore`, never `SqliteStore`.

```bash
uv run pytest engine
```

- Web checks run the TypeScript compiler.

```bash
pnpm --dir web run test
```

- The eval runner prints recall@5. `--bm25-only` skips embeddings.

```bash
uv run python eval/run.py --bm25-only
```

## Team workflow

- Get the code and your branch.

```bash
git fetch origin
git checkout dev-<yourname>
git merge origin/dev-law
```

- Open `docs/PLAN.md` and find your name.
- "Who blocks whom" says what to push first. "Order of work" says what to do at each clock mark.
- Read `AGENTS.md`. Then read only the `contracts/` files your tasks mention.
- Kick off your agent in the repo root. Paste this with your name and letter.

```
I am <name>, owner of workstream <letter> in docs/PLAN.md. Read AGENTS.md,
contracts/README.md, and my section of docs/PLAN.md. Tell me which of my tasks are [A]
and can start now, which [H] task I do first, and whether `uv sync --extra dev` and
`aws sts get-caller-identity` pass on this machine. Do not write code yet.
```

- For each [A] task it names, open a fresh session and paste that task's block from `docs/AGENT-PROMPTS.md`.
- One task per session. Keep your main session for your [H] task.
- Commit small and push often. Merge to `dev-law` when a task is done.
- If your task is one of the three gates in the plan, push the moment it works and say so in the chat.

- Do not edit another workstream's package. Stub it with `TODO(<letter>)`.
- Tell the group before changing anything in `contracts/`.
- Blocked more than 10 minutes? Say so in the chat.
- Checkpoint 1:30. One PDF in, one cited answer out, shown in the UI. Protect this over any feature.
- Checkpoint 3:00. Feature freeze.
- Checkpoint 3:30. Demo rehearsed twice, backup recording made.
- Checkpoint 4:00. Submitted.
