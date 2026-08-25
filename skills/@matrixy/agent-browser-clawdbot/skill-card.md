## Description: <br>
Headless browser automation CLI optimized for AI agents with accessibility tree snapshots and ref-based element selection. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[matrixy](https://clawhub.ai/user/matrixy) <br>

### License/Terms of Use: <br>


## Use Case: <br>
Developers and AI agents use this skill to automate browser workflows through the agent-browser CLI, including navigation, accessibility-tree snapshots, ref-based interactions, data extraction, session isolation, and browser state persistence. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill depends on an external agent-browser package source. <br>
Mitigation: Install it only when the package source is trusted and keep the CLI installation under normal software supply-chain controls. <br>
Risk: Saved browser state, cookies, and storage can expose sensitive account data. <br>
Mitigation: Use isolated sessions or test accounts where possible, keep auth files out of source control and logs, restrict file permissions, and avoid dumping or changing production or personal account cookies and storage unless necessary. <br>


## Reference(s): <br>
- [Agent Browser project homepage](https://github.com/vercel-labs/agent-browser) <br>
- [ClawHub skill page](https://clawhub.ai/matrixy/skills/agent-browser-clawdbot) <br>


## Skill Output: <br>
**Output Type(s):** [Shell commands, Guidance, JSON, Files] <br>
**Output Format:** [Markdown guidance with bash command examples and JSON browser snapshot examples] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Can produce or manipulate browser state files, screenshots, PDFs, cookies, storage values, and network request data through the external CLI.] <br>

## Skill Version(s): <br>
0.1.0 (source: server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
