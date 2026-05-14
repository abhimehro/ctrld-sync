import re
import os

for root, _, files in os.walk(".github"):
    for file in files:
        if file.endswith(".yml") or file.endswith(".yaml"):
            path = os.path.join(root, file)
            with open(path, "r") as f:
                content = f.read()
            if "pull-request-reviewer" in content or "github/copilot" in content or "agentics-maintenance" in content or "copilot_t_ci" in content or "copilot" in content.lower():
                print(f"Found something in {path}")
