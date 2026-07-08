# projects/

Automation projects live here, per [`CLAUDE.md`](../CLAUDE.md). Each project
is self-contained: its own folder, its own README, its own run/test commands.

## Convention for a new project

```
projects/<project-name>/
├── README.md          # what it does, setup, run command, test command
├── requirements.txt    # or package.json — dependencies, if any
├── <entry script>       # e.g. run.py, run.ps1
└── tests/               # or a test command documented in README
```

When you build one, `README.md` must answer:

1. **What it does** — one paragraph.
2. **Setup** — how to install dependencies / configure `.env` (never commit
   secrets — see root `.gitignore`).
3. **Run command** — the exact command to start it.
4. **Test command** — the exact command to verify it still works.
5. **How OpenClaw should call it** — heartbeat, cron, a skill wrapper, or
   manual-only. Be explicit; see [`../scripts/README.md`](../scripts/README.md)
   for the heartbeat-vs-cron decision rule from `AGENTS.md`.

## Existing projects (legacy exception)

`invoice_extractor/` and `receipt_extractor/` were built before this
`projects/` convention existed and **intentionally remain at the workspace
root**, not moved here. `invoice_extractor` backs a **live Windows Scheduled
Task** ("Invoice Extractor Bot") that references its absolute path directly —
moving the folder without also updating the scheduled task would silently
kill a running production bot. Treat both as legacy, root-level projects;
any *new* automation should go under `projects/`.

## Current projects

- [`workspace-health-check/`](workspace-health-check/) — checks git status,
  the two live scheduled tasks, data-folder disk usage, and `.env` presence
  for the bots; reports PASS/WARN/FAIL.
