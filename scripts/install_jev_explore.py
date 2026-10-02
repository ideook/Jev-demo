import json
import os
from pathlib import Path
import shutil
import sys

workspace = Path(__file__).resolve().parent.parent
source = workspace / "skills" / "jev-explore"
deliverables = workspace / ".runtime" / "installations" / "jev-explore"
codex_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
destination = codex_root / "skills" / "jev-explore"
files = ["SKILL.md", "agents/openai.yaml", "scripts/jev_rank.py", "scripts/jev_explore_hook.py"]
if destination.is_symlink() or not destination.resolve().is_relative_to(codex_root / "skills"):
    raise SystemExit("Unexpected skill destination; refusing to install")
if destination.exists():
    for name in files:
        target = destination / name
        if not target.is_file() or target.read_bytes() != (source / name).read_bytes():
            raise SystemExit("An existing jev-explore skill differs; refusing to overwrite it")
else:
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
python = Path(sys.executable).resolve().as_posix()
script = (destination / "scripts" / "jev_explore_hook.py").as_posix()
command = f'"{python}" "{script}"'
definition = {"matcher": "^Bash$", "hooks": [{"type": "command", "command": command, "commandWindows": command, "timeout": 5, "statusMessage": "Jev Explore: source reading priorities", "additionalContextLimit": 1200}]}
hook_path = codex_root / "hooks.json"
config = json.loads(hook_path.read_text(encoding="utf-8-sig")) if hook_path.exists() else {}
groups = config.setdefault("hooks", {}).setdefault("PostToolUse", [])
matching = [group for group in groups if any(script in item.get("command", "") for item in group.get("hooks", []))]
if len(matching) > 1 or matching and matching[0] != definition:
    raise SystemExit("An existing Jev Explore hook differs; refusing to overwrite it")
if not matching:
    groups.append(definition)
    temporary = hook_path.with_name("hooks.json.jev-explore.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(hook_path)
deliverables.mkdir(parents=True, exist_ok=True)
(deliverables / "hook-registration.json").write_text(json.dumps({"hooks": {"PostToolUse": [definition]}}, indent=2) + "\n", encoding="utf-8")
output = {"installed": True, "skill_path": str(destination), "hook_path": str(hook_path), "matcher": "^Bash$", "trust_review_required": True, "preserved_existing_hook_groups": len(groups) - 1}
(deliverables / "installation.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
print(json.dumps(output, indent=2))
