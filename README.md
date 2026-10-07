# Rujuk

Intelligent document search and Q&A for government agencies. AWS hackathon, 4-hour build.

## Start here (10 minutes)

1. **Get the code**

   ```bash
   git fetch origin
   git checkout -b <yourname>/dev origin/dev-law
   ```

2. **Find your name and your tasks.** Open `docs/PLAN.md`. Each workstream has a name on
   it: A Malissa, B Noah, C Cyndia, D Lawrence. Your table lists your tasks in order,
   with a mode, a time target, and a "done when" column. That column is the definition of
   finished; nothing else is.

3. **Read the two short files everyone must know.** `AGENTS.md` (rules, layout, stack,
   commands) and `contracts/README.md` (the data shapes that cross between workstreams).
   Then skim only the contract files your tasks mention.

4. **Set up the machine.**

   ```bash
   uv sync --extra dev
   cp .env.example .env
   aws sts get-caller-identity
   ```

   Fill in `AWS_PROFILE` and `AWS_REGION` in `.env`. Then open the Bedrock console for that
   region and check Model access for Titan Text Embeddings v2 and the Claude models named
   in `.env`. If one is missing, say so in the group chat now, not at the 1:30 checkpoint.

   Lawrence only: `cd web` happens after task D1 creates it, not before.

5. **Start your first task.** Look at the `Mode` column.
   - **[A]**: open `docs/AGENT-PROMPTS.md`, find the block with your task ID, paste it into
     your agent (Claude Code, Kiro, Cursor, DeepSeek, any of them). The agent reads
     `AGENTS.md` and the contracts itself. Review the diff, run the test command, commit.
   - **[H]**: do it yourself. If it names a prompt file (A4, C3), that file has the full
     prompt text, the output schema, and the test questions.

   Run your [A] tasks that have no dependency all at once, then do your [H] task while
   the agents work. The dependency graph is in `docs/PLAN.md` under "Dependencies".

6. **Commit small, push often.**

   ```bash
   git add -A && git commit -m "<area>: <what>" && git push -u origin <yourname>/dev
   ```

   Open a PR to `dev-law` when a task is done. One reviewer, merge fast.

## The only rules that will bite you

- Do not edit another workstream's package. Stub what you need with `TODO(<letter>)`.
- Every chunk must have a page number.
- Change a file in `contracts/` only after telling the group.
- `.env` never gets committed.

## Checkpoints

| Clock | Must be true |
|---|---|
| 1:30 | One PDF in, one cited answer out, shown in the UI |
| 3:00 | Feature freeze |
| 3:30 | Demo rehearsed twice, backup recording made |
| 4:00 | Submitted |

If you are blocked for more than 10 minutes, say so in the group chat. Protect the 1:30
checkpoint over any feature.

## Map

```
docs/BRAINSTORM.md       why we are building this and what we decided
docs/PLAN.md             who does what, in what order, done-when per task
docs/AGENT-PROMPTS.md    paste-ready prompts for every agent-delegable task
docs/prompts/            seed corpus generation prompt
AGENTS.md                rules for humans and agents, shared by every tool
contracts/               data shapes and the API contract
engine/ingest/           A: file -> chunks            (prompts/ has the tagger prompt)
engine/index/            B: store and hybrid search
api/                     C: FastAPI                   (prompts/ has the answer prompt)
web/                     D: Next.js (created by task D1)
samples/                 synthetic seed corpus
eval/                    retrieval eval questions and runner
```
