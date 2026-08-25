## Description: <br>
Get current weather and forecasts (no API key required). <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[steipete](https://clawhub.ai/user/steipete) <br>

### License/Terms of Use: <br>


## Use Case: <br>
Developers and external users use this skill to ask an agent for current weather, compact conditions, full forecasts, or programmatic weather JSON using public weather services. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: Weather location queries are sent to external public weather services. <br>
Mitigation: Avoid sensitive exact locations in restricted environments and review requested locations before execution. <br>
Risk: Forecast results depend on third-party service availability and returned data quality. <br>
Mitigation: Treat results as external weather-service output and verify critical weather decisions against authoritative local sources. <br>


## Reference(s): <br>
- [wttr.in help](https://wttr.in/:help) <br>
- [Open-Meteo documentation](https://open-meteo.com/en/docs) <br>


## Skill Output: <br>
**Output Type(s):** [shell commands, guidance] <br>
**Output Format:** [Markdown with inline bash code blocks and weather-service URLs] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Uses public weather services; no API key is required; requires curl.] <br>

## Skill Version(s): <br>
1.0.0 (source: server release evidence) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
