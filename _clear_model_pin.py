import json
import os

path = os.path.expanduser(r"~\.openclaw\agents\main\sessions\sessions.json")

with open(path, encoding="utf-8") as f:
    data = json.load(f)

entry = data.get("agent:main:main", {})

# Check for model override fields
for k in ("model", "modelProvider", "authProfileOverride", "liveModelSwitchPending", "contextTokens"):
    if k in entry:
        print(f"{k}: {entry[k]}")

# Print last 5 keys
keys = list(entry.keys())
print("---")
for k in keys[-5:]:
    v = entry[k]
    if isinstance(v, (str, int, float, bool)):
        print(f"{k}: {v}")
    else:
        print(f"{k}: {type(v).__name__}")

# Check if there's a model override or pinned model field
for k in keys:
    if "model" in k.lower() and k != "model":
        print(f"model-related field: {k} = {entry[k]}")
    if "pinned" in k.lower():
        print(f"pinned field: {k} = {entry[k]}")