"""Install North Star's user-scope skill and native hooks, preserving other hooks."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys

REPO = Path(__file__).resolve().parent.parent
SOURCES = {
    "north-star/north_star.py": "hooks/north-star/north_star.py",
    "north-star/automatic.py": "hooks/north-star/automatic.py",
    "skills/north-star/SKILL.md": "skills/north-star/SKILL.md",
    "skills/north-star/LICENSE": "hooks/north-star/upstream/LICENSE",
    "skills/north-star/UPSTREAM.md": "hooks/north-star/UPSTREAM.md",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def definitions(root):
    args = [Path(sys.executable).resolve().as_posix(), "-X", "utf8",
            (root / "north-star/north_star.py").as_posix(), "--root", (root / "north-star").as_posix(), "hook"]
    command = shlex.join(args)
    windows_command = None
    if os.name == "nt":
        quoted = " ".join("'" + arg.replace("'", "''") + "'" for arg in args)
        wrapper = (
            "$ProgressPreference = 'SilentlyContinue'; $utf8 = [System.Text.UTF8Encoding]::new($false); "
            "[Console]::InputEncoding = $utf8; [Console]::OutputEncoding = $utf8; $OutputEncoding = $utf8; "
            f"& {quoted}; exit $LASTEXITCODE"
        )
        encoded = base64.b64encode(wrapper.encode("utf-16le")).decode("ascii")
        windows_command = f"powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand {encoded}"
    result = {}
    for name in ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "PreCompact", "PostCompact"):
        hook = {"type": "command", "command": command, "timeout": 12}
        if windows_command:
            hook["commandWindows"] = windows_command
        if name in ("SessionStart", "UserPromptSubmit", "PostToolUse"):
            hook["additionalContextLimit"] = 1800
        group = {"description": "North Star: source-backed task continuity", "hooks": [hook]}
        result[name] = group
    return result


def install(root, allow_export=False, preserve_config=False):
    if preserve_config and allow_export:
        raise ValueError("Preserve config cannot also change export consent")
    root = root.absolute()
    paths = [root, root / "hooks.json", root / "north-star", root / "skills",
             root / "skills/north-star", *[root / x for x in SOURCES],
             root / "north-star/config.json", root / "north-star/installation.json"]
    if any(p.is_symlink() for p in paths):
        raise ValueError("Refusing symlinked installation destination")
    root = root.resolve()
    hook_path = root / "hooks.json"
    temporary = hook_path.with_name("hooks.json.north-star.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("Refusing existing temporary hook file")
    if any(not (REPO / source).is_file() for source in SOURCES.values()):
        raise ValueError("Missing installation source")
    old = json.loads(hook_path.read_text(encoding="utf-8-sig")) if hook_path.exists() else {}
    if not isinstance(old, dict) or not isinstance(old.get("hooks", {}), dict):
        raise ValueError("Invalid hooks configuration")
    manifest_path = root / "north-star/installation.json"
    prior = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.exists() else {}
    defs = definitions(root)
    merged = json.loads(json.dumps(old))
    for name, group in defs.items():
        groups = merged.setdefault("hooks", {}).setdefault(name, [])
        if not isinstance(groups, list):
            raise ValueError("Invalid event configuration")
        matching = [g for g in groups if any("north-star/north_star.py" in h.get("command", "").replace("\\", "/") for h in g.get("hooks", []))]
        if len(matching) > 1 or (matching and matching[0] not in (group, prior.get("hooks", {}).get(name))):
            raise ValueError("Conflicting North Star hook; preserve and review it")
        if matching:
            groups[groups.index(matching[0])] = group
        else:
            groups.append(group)
    for target, source in SOURCES.items():
        p = root / target
        if p.exists() and sha(p) not in (sha(REPO / source), prior.get("files_sha256", {}).get(target)):
            raise ValueError("Local changes in " + target)
    settings_path = root / "north-star/config.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8-sig")) if settings_path.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError("Invalid existing North Star settings")
    if preserve_config:
        if not settings_path.is_file():
            raise ValueError("Preserve config requires an existing installation")
    else:
        settings.update(allow_export=allow_export, mode="conditional", automatic_goals=True, model="jev-1.14.0",
                        env_file=str(Path.home() / ".config/typesafe/env"),
                        transcript_roots=[str(root / "sessions"), str(root / "archived_sessions")])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = root / "north-star/backups" / stamp
    backup.mkdir(parents=True, mode=0o700)
    for p in [hook_path, settings_path, manifest_path, *[root / x for x in SOURCES]]:
        if p.exists():
            dest = backup / p.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(p, dest)
            dest.chmod(0o600)
    for target, source in SOURCES.items():
        p = root / target
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        p.write_bytes((REPO / source).read_bytes())
        p.chmod(0o600)
    if not preserve_config:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        settings_path.chmod(0o600)
    temporary.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(hook_path)
    receipt = {"installed_at": stamp, "backup": str(backup), "hooks": defs,
               "files_sha256": {x: sha(root / x) for x in SOURCES},
               "allow_export": settings.get("allow_export", False), "mode": settings.get("mode", "conditional"),
               "config_preserved": preserve_config, "trust_review_required": True}
    manifest_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    p.add_argument("--allow-export", action="store_true",
                   help="Authorize capped redacted goals, human source excerpts and recent conversation to TypeSafe")
    p.add_argument("--preserve-config", action="store_true",
                   help="Update installed code/skill while preserving existing config bytes and export consent")
    args = p.parse_args()
    print(json.dumps(install(args.codex_home, args.allow_export, args.preserve_config), indent=2))
