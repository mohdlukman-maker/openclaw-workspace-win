# workspace-health-check

Reports the health of this OpenClaw workspace in one pass: whether the git
checkpoint is clean, whether the two live scheduled tasks (Invoice Extractor
Bot, Jarvis Folder Organizer) are in the expected state, whether the bot data
folders are growing too large, and whether both bots' `.env` files exist.

Built after discovering (during a workspace restructure) that
`invoice_extractor` is backed by a live Windows Scheduled Task with an
absolute path dependency, and that its `data/cleanup_archive` folder was
already past a sane size. This script makes that kind of drift visible at a
glance instead of by accident.

## What it does

- **Git checkpoint** - PASS if the workspace git repo has a clean working
  tree, WARN with a count if there are uncommitted changes.
- **Scheduled tasks** - checks `Invoice Extractor Bot` and
  `Jarvis Folder Organizer` exist and report their state/last-run-result.
  FAIL if a task is missing entirely.
- **Data folder size** - flags `invoice_extractor/data/{cleanup_archive,ocr,enhanced}`
  if they exceed `-DataWarnMB` (default 300MB), since these are meant to be
  pruned by the bot's own retention logic.
- **.env presence** - FAIL if `invoice_extractor/.env` or
  `receipt_extractor/.env` is missing (existence check only - never reads
  the contents).

## Run command

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Check-WorkspaceHealth.ps1
```

Optional: raise/lower the data-size warning threshold:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Check-WorkspaceHealth.ps1 -DataWarnMB 500
```

Exit code: `0` = all PASS, `1` = at least one WARN, `2` = at least one FAIL.

## Test command

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Check-WorkspaceHealth.ps1 -SelfTest
```

Runs every check function and asserts none of them throw on this machine.
Exits `0` on success, `1` if any check function errors.

## How OpenClaw should call it

- **Heartbeat**: not a fit - this is a point-in-time diagnostic, not
  something needing conversational context.
- **Cron**: register a daily/weekly Windows Scheduled Task (or ask the agent
  to run it manually) and only surface a message to Lukman if the exit code
  is non-zero (WARN or FAIL). Silence on PASS keeps this quiet per
  `AGENTS.md`'s "don't be noisy" guidance.
- **Manual**: run it any time before/after touching `invoice_extractor` or
  `receipt_extractor`, or after a workspace restructure, as a quick
  did-I-break-anything check.
