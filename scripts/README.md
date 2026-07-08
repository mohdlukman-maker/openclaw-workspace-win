# scripts/

Standalone executable helper scripts that aren't full automation projects
(no data/dependencies of their own) - system-level utilities, per
[`CLAUDE.md`](../CLAUDE.md). Multi-file automations with their own data/deps
belong under [`../projects/`](../projects/) instead.

## Organize-DesktopDownloads.ps1

Sorts aged files (default: older than 24h) on the Desktop and in Downloads
into category subfolders (by filename keywords, falling back to file
extension). Never touches files newer than the age cutoff, `.lnk` shortcuts,
or `desktop.ini`/`Thumbs.db`. Logs every action to `../logs/`.

**Run command:**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Organize-DesktopDownloads.ps1
```

**Dry run (no files moved, only logged):**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Organize-DesktopDownloads.ps1 -DryRun
```

**Test command:** none dedicated - use `-DryRun` against the real
Desktop/Downloads to verify categorization before trusting a real run.

**How OpenClaw should call it:** already registered as the **"Jarvis Folder
Organizer"** Windows Scheduled Task, running daily. This is the cron pattern
from `AGENTS.md`: exact daily timing, no conversational context needed. Do
not duplicate this as a heartbeat check.

**Live dependency:** the Scheduled Task action points at this file's
absolute path (`...\workspace\scripts\Organize-DesktopDownloads.ps1`). If you
ever move or rename this script, update the scheduled task's action in the
same change, or the daily run will silently stop working.
