## Description: <br>
Captures learnings, errors, and corrections to enable continuous improvement for the agent. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[pskoett](https://clawhub.ai/user/pskoett) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
Developers and agent users use this skill to capture corrections, command failures, feature requests, and reusable workflow lessons in local learning files. OpenClaw users can optionally enable a hook that injects reminders and scans ended sessions for error snippets to triage later. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Persistent local learning files may contain sensitive project context if users or agents log too much detail. <br>
Mitigation: Keep .learnings out of version control, review entries before sharing workspaces, and record short redacted summaries rather than secrets, raw transcripts, or full command output. <br>
Risk: The optional OpenClaw hook can scan ended session transcripts for error snippets. <br>
Mitigation: Enable the hook only in trusted workspaces, avoid it for sessions containing credentials or customer data, and rely on its opt-in .learnings directory behavior to disable scanning when needed. <br>


## Reference(s): <br>
- [ClawHub skill page](https://clawhub.ai/pskoett/skills/self-improving-agent) <br>
- [OpenClaw integration guide](references/openclaw-integration.md) <br>
- [Entry examples](references/examples.md) <br>
- [Uninstall guide](references/uninstall.md) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, code, shell commands, configuration, guidance] <br>
**Output Format:** [Markdown guidance with inline shell commands and file templates] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Creates or appends local learning files when used; optional OpenClaw hook writes redacted session-end error excerpts.] <br>

## Skill Version(s): <br>
4.0.1 (source: server release metadata; artifact frontmatter reports 4.0.0) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
