import json
import os
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parent.parent
demo = workspace / "hooks" / "jev-hook-demo"
python = Path(sys.executable).resolve().as_posix()
script = (demo / "jev_judge_hook.py").as_posix()
definition = {
    "matcher": "^apply_patch$",
    "hooks": [{
        "type": "command",
        "command": f'"{python}" "{script}"',
        "commandWindows": f'"{python}" "{script}"',
        "timeout": 30,
        "statusMessage": "Jev demo: checking rule test coverage",
        "additionalContextLimit": 1500,
    }],
}
deliverables = workspace / ".runtime" / "installations" / "jev-judge"
deliverables.mkdir(parents=True, exist_ok=True)
(deliverables / "hook-registration.json").write_text(json.dumps({"hooks": {"PostToolUse": [definition]}}, indent=2) + "\n", encoding="utf-8")
destination = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "hooks.json"
config = json.loads(destination.read_text(encoding="utf-8-sig")) if destination.exists() else {}
groups = config.setdefault("hooks", {}).setdefault("PostToolUse", [])
matching = [group for group in groups if any(script in item.get("command", "") for item in group.get("hooks", []))]
if len(matching) > 1:
    raise SystemExit("Duplicate Jev demo hooks found; refusing to register another")
if matching and matching[0] != definition:
    raise SystemExit("An existing Jev demo hook differs; refusing to overwrite it")
if not matching:
    groups.append(definition)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("hooks.json.jev-demo.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
print(json.dumps({"registered": True, "path": str(destination), "event": "PostToolUse", "matcher": "^apply_patch$", "scope": str(demo), "trust_review_required": True}))
