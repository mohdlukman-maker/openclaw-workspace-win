\# Claude Code Workspace Instructions



This is the active OpenClaw workspace.



You may work aggressively inside this workspace:

\- Create files and folders.

\- Edit scripts.

\- Refactor project code.

\- Write documentation.

\- Create OpenClaw skills.

\- Build automation workflows.

\- Run tests and diagnostics.

\- Improve project structure.



Priority:

1\. Keep OpenClaw operational.

2\. Keep secrets safe.

3\. Prefer small, reversible changes.

4\. Explain major changes before applying them.

5\. Use Git before large refactors.



Do not modify:

\- ../openclaw.json

\- ../secrets/

\- ../agents/

\- .env

\- .env.\*

\- credentials.json

\- \*.key

\- \*.token

\- \*.sqlite



For OpenClaw integration:

\- AGENTS.md controls OpenClaw agent behavior.

\- TOOLS.md documents local tools and command conventions.

\- skills/ contains custom OpenClaw skills.

\- scripts/ contains executable helper scripts.

\- projects/ contains actual automation projects.



When building an automation:

1\. Create a project folder under projects/.

2\. Add README.md.

3\. Add a test command.

4\. Add a simple run command.

5\. Document how OpenClaw should call it.

