# skills/

Custom OpenClaw skills that are specific to this workspace (as opposed to
shared/built-in skills that ship with OpenClaw or come from a plugin).

Referenced by [`AGENTS.md`](../AGENTS.md): "Skills provide your tools. When
you need one, check its `SKILL.md`."

## Layout

Each skill is its own folder containing a `SKILL.md`:

```
skills/
└── <skill-name>/
    └── SKILL.md      # description + trigger conditions + instructions
    └── ... (scripts/assets the skill needs)
```

Built-in/plugin skills are installed under
`~/.openclaw/plugin-skills/` (symlinked in, one level above this
workspace) — do not duplicate those here. This folder is only for
skills unique to this machine/workspace.

## Adding a skill

1. Create `skills/<skill-name>/SKILL.md`.
2. Give it a clear `description` (used for auto-triggering) and concrete
   trigger phrases.
3. Keep any helper scripts the skill needs alongside it in the same folder.
4. If the skill wraps a project in `projects/`, link to that project's
   README rather than duplicating instructions.

No skills exist yet — this folder was scaffolded so the next automation
that deserves a skill wrapper has a home.
