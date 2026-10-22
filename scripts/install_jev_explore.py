"""Install on-demand Explore and remove its legacy per-shell callback."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import uuid

WORKSPACE = Path(__file__).resolve().parent.parent
SOURCE = WORKSPACE / "skills" / "jev-explore"
FILES = ("SKILL.md", "agents/openai.yaml", "scripts/jev_rank.py")


def remove_legacy_hook(config, script):
    """Recognize our installed handler by its full command path, not its label."""
    if not isinstance(config, dict) or not isinstance(config.get("hooks", {}), dict):
        raise ValueError("Invalid hooks configuration")
    groups = config.get("hooks", {}).get("PostToolUse", [])
    if not isinstance(groups, list):
        raise ValueError("Invalid PostToolUse configuration")
    removed = 0
    retained = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            raise ValueError("Invalid PostToolUse group")
        hooks = []
        for hook in group["hooks"]:
            if not isinstance(hook, dict):
                raise ValueError("Invalid PostToolUse hook")
            command = hook.get("command", "")
            try:
                tokens = shlex.split(command.replace("\\", "/")) if isinstance(command, str) else []
            except ValueError:
                tokens = []
            owned = (hook.get("type") == "command" and len(tokens) >= 2
                     and os.path.normcase(tokens[-1]) == os.path.normcase(script)
                     and Path(tokens[0]).name.lower().startswith("python")
                     and tokens[1:-1] in ([], ["-X", "utf8"]))
            if owned:
                if len(group["hooks"]) != 1:
                    raise ValueError("Legacy Explore shares a customized group; refusing to shift other hooks' trust keys")
                removed += 1
            else:
                hooks.append(hook)
        # Native trust keys include group indexes. Keep an empty slot so removing
        # Explore does not invalidate trust for the following North Star hook.
        retained.append(group | {"hooks": hooks})
    if removed:
        config["hooks"]["PostToolUse"] = retained
    return removed


def install(codex_root, update=False):
    codex_root = codex_root.resolve()
    destination = codex_root / "skills" / "jev-explore"
    hook_path = codex_root / "hooks.json"
    if destination.is_symlink() or not destination.resolve().is_relative_to(codex_root / "skills") or hook_path.is_symlink():
        raise ValueError("Unexpected installation destination")
    # Finish validation before updating either the skill or hook registrations.
    config = json.loads(hook_path.read_text(encoding="utf-8-sig")) if hook_path.exists() else {}
    legacy = (destination / "scripts" / "jev_explore_hook.py").as_posix()
    removed = remove_legacy_hook(config, legacy)
    changed = []
    for name in FILES:
        target = destination / name
        if target.is_symlink() or not target.resolve().is_relative_to(destination):
            raise ValueError("Unexpected skill file destination")
        if target.exists() and not target.is_file():
            raise ValueError("Skill file destination is not a regular file")
        if not target.exists() or target.read_bytes() != (SOURCE / name).read_bytes():
            if destination.exists() and not update:
                raise ValueError("An existing jev-explore skill differs; inspect it and use --update to back up and replace managed files")
            changed.append(name)
    backup = None
    if removed or any((destination / name).exists() for name in changed):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        backup = codex_root / "backups" / "jev-explore" / stamp
        backup.mkdir(parents=True)
        if removed:
            shutil.copy2(hook_path, backup / "hooks.json")
        for name in changed:
            if (destination / name).exists():
                saved = backup / "skills" / "jev-explore" / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination / name, saved)
    for name in changed:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / name, target)
    if removed:
        temporary = hook_path.with_name(f"hooks.json.jev-explore-{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(hook_path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"installed": True, "mode": "on_demand", "skill_path": str(destination),
            "hook_path": str(hook_path), "removed_legacy_hooks": removed,
            "updated_files": changed, "backup_path": str(backup) if backup else None,
            "trust_review_required": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))))
    parser.add_argument("--update", action="store_true", help="Back up and replace differing managed skill files")
    args = parser.parse_args()
    try:
        output = install(args.codex_home, args.update)
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
    records = WORKSPACE / ".runtime" / "installations" / "jev-explore"
    records.mkdir(parents=True, exist_ok=True)
    (records / "installation.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (records / "hook-registration.json").write_text('{"hooks": {"PostToolUse": []}}\n', encoding="utf-8")
    # ASCII JSON stays readable by UTF-8 callers even on legacy Windows consoles.
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
