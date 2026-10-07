# Rujuk

Document search and Q&A for government agencies. AWS hackathon, 4-hour build.

## Start here

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
