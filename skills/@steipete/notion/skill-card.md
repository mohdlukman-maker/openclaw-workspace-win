## Description: <br>
Notion API for creating and managing pages, databases, and blocks. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[steipete](https://clawhub.ai/user/steipete) <br>

### License/Terms of Use: <br>


## Use Case: <br>
Developers and agents use this skill to work with a Notion integration for creating, reading, updating, and querying pages, data sources, and blocks. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: A Notion API token could expose workspace data if stored or shared insecurely. <br>
Mitigation: Use a dedicated integration, store the token at ~/.config/notion/api_key with restrictive permissions, and avoid sharing the token in prompts, logs, or repositories. <br>
Risk: Write-capable POST and PATCH examples can change pages, data sources, or blocks in a real workspace. <br>
Mitigation: Review write commands before execution and share only the specific pages or databases the integration needs. <br>


## Reference(s): <br>
- [Notion Developer Documentation](https://developers.notion.com) <br>
- [Notion Integrations](https://notion.so/my-integrations) <br>


## Skill Output: <br>
**Output Type(s):** [Guidance, Shell commands, API calls, Configuration] <br>
**Output Format:** [Markdown with inline bash and JSON examples] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Includes curl examples for Notion API operations and local API key setup guidance.] <br>

## Skill Version(s): <br>
1.0.0 (source: server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
