## Description: <br>
Transform AI agents from task-followers into proactive partners that anticipate needs and continuously improve with WAL Protocol, Working Buffer, autonomous cron patterns, and security hardening. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[halthelobster](https://clawhub.ai/user/halthelobster) <br>

### License/Terms of Use: <br>
MIT <br>


## Use Case: <br>
Developers and agent operators use this skill to configure assistants that maintain persistent context, recover from compaction, proactively surface useful work, and apply guardrails for external content, deletion, cron jobs, and self-improvement. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill encourages persistent personal context and monitoring of sensitive sources. <br>
Mitigation: Use explicit opt-in for monitored sources and provide a clear way to inspect, edit, and delete stored memory. <br>
Risk: The skill can prompt agents toward local cleanup, cron reminders, and spawned-agent workflows that may act without enough scoping. <br>
Mitigation: Require previews and human approval before deleting, trashing, sending, posting, or delegating sensitive tasks. <br>
Risk: The skill may capture tool configuration and credential-location notes. <br>
Mitigation: Store only credential locations or handling rules, never secret values, and constrain file permissions before enabling broad local-tool access. <br>


## Reference(s): <br>
- [Proactive Agent ClawHub Page](https://clawhub.ai/halthelobster/skills/proactive-agent) <br>
- [Onboarding Flow Reference](references/onboarding-flow.md) <br>
- [Security Patterns Reference](references/security-patterns.md) <br>
- [Clawdbot GitHub Repository](https://github.com/clawdbot/clawdbot) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, shell commands, configuration, guidance] <br>
**Output Format:** [Markdown guidance with inline shell commands and configuration examples] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [May guide agents to create or update local memory, onboarding, tool, heartbeat, and audit files.] <br>

## Skill Version(s): <br>
3.1.0 (source: server release and SKILL.md frontmatter) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
