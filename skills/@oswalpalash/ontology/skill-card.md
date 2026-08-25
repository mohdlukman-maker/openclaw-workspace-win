## Description: <br>
Typed knowledge graph for structured agent memory and composable skills. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[oswalpalash](https://clawhub.ai/user/oswalpalash) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
Developers and agents use this skill to keep durable structured memory as a typed, constraint-validated graph. It supports creating, querying, linking, and validating entities such as people, projects, tasks, events, documents, credentials, actions, and policies. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill intentionally persists user-supplied structured memory in local ontology files. <br>
Mitigation: Use it only when durable local memory is desired and periodically review memory/ontology/graph.jsonl and memory/ontology/schema.yaml. <br>
Risk: Secrets or sensitive credentials could be captured if users store raw values in ontology entities. <br>
Mitigation: Store secret references only, not passwords, tokens, API keys, or raw secret values. <br>
Risk: Append-only history can retain information even after update or delete operations are represented later in the log. <br>
Mitigation: Treat the graph log as persistent history and sanitize or rotate the file when retained data should no longer remain in the workspace. <br>
Risk: Shared ontology state may be read or reused by other skills in the same workspace. <br>
Mitigation: Keep the graph scoped to data appropriate for cross-skill access and inspect it before sharing or packaging the workspace. <br>


## Reference(s): <br>
- [ClawHub Skill Page](https://clawhub.ai/oswalpalash/skills/ontology) <br>
- [Ontology Schema Reference](references/schema.md) <br>
- [Query Reference](references/queries.md) <br>


## Skill Output: <br>
**Output Type(s):** [text, markdown, code, shell commands, configuration, guidance] <br>
**Output Format:** [Markdown guidance with JSON, YAML, Python, and shell command examples; CLI operations emit JSON or plain status text.] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Creates and updates local JSONL graph data and YAML schema files under memory/ontology by default.] <br>

## Skill Version(s): <br>
1.0.4 (source: server release evidence) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
