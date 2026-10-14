"""Install the skill picker and merge only its UserPromptSubmit registration."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys

WORKSPACE = Path(__file__).resolve().parent.parent


def register(codex_root: Path, env_file: Path | None = None, allow_prompt_export: bool = False) -> dict:
    codex_root = codex_root.resolve()
    directory = codex_root / "hooks"
    script = directory / "jev-skill-pick.py"
    settings = script.with_suffix(".json")
    hook_path = codex_root / "hooks.json"
    if any(path.is_symlink() for path in (directory, script, settings, hook_path)):
        raise ValueError("Refusing to replace a symlinked hook destination")
    source = WORKSPACE / "hooks" / "jev-skill-pick" / "jev_skill_pick.py"
    if script.exists() and script.read_bytes() != source.read_bytes():
        raise ValueError("Installed picker differs; review it before replacing")
    config = json.loads(hook_path.read_text(encoding="utf-8-sig")) if hook_path.exists() else {}
    definition = {"hooks": [{
        "type": "command", "command": f'"{Path(sys.executable).resolve().as_posix()}" "{script.as_posix()}"',
        "timeout": 25, "statusMessage": "Jev: selecting a relevant Codex skill", "additionalContextLimit": 600,
    }]}
    groups = config.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    matching = [g for g in groups if any(str(script) in h.get("command", "") for h in g.get("hooks", []))]
    if len(matching) > 1 or matching and matching[0] != definition:
        raise ValueError("A conflicting Jev skill picker hook is already registered")
    local = {"model": "jev-latest", "min_confidence": 0.8, "codex_command": shutil.which("codex") or "codex",
        "allow_prompt_export": allow_prompt_export}
    if env_file:
        local["env_file"] = str(env_file.resolve())
    if settings.exists() and json.loads(settings.read_text()) != local:
        raise ValueError("Installed picker settings differ; review them before replacing")
    directory.mkdir(parents=True, exist_ok=True)
    if not script.exists():
        shutil.copy2(source, script)
    if not settings.exists():
        settings.write_text(json.dumps(local, indent=2) + "\n")
        settings.chmod(0o600)
    if not matching:
        if hook_path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = hook_path.with_name(f"hooks.json.before-jev-skill-pick-{stamp}")
            shutil.copy2(hook_path, backup)
        groups.append(definition)
        temporary = hook_path.with_name("hooks.json.jev-skill-pick.tmp")
        temporary.write_text(json.dumps(config, indent=2) + "\n")
        temporary.replace(hook_path)
    return {"registered": True, "event": "UserPromptSubmit", "script_path": str(script),
        "hook_path": str(hook_path), "settings_path": str(settings), "trust_review_required": True,
        "allow_prompt_export": allow_prompt_export}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    parser.add_argument("--env-file", type=Path, help="Explicit fallback credential file; stores only its path")
    parser.add_argument("--allow-prompt-export", action="store_true", help="Opt in to sending prompts and skill descriptions to TypeSafe")
    args = parser.parse_args()
    print(json.dumps(register(args.codex_home, args.env_file, args.allow_prompt_export), indent=2))


if __name__ == "__main__":
    main()
