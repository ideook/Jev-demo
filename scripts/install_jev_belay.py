"""Install the reviewed Codex adapter, preserving unrelated hooks and credentials."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil

WORKSPACE = Path(__file__).resolve().parent.parent
SOURCE = WORKSPACE / "hooks" / "jev-belay"
COMMIT = "c59f030032baedb3a3e5acefd3ead19d9dcde84c"
FILES = ["codex.mjs", "codex-evidence.mjs", "upstream/belay.mjs", "upstream/tui.mjs", "upstream/LICENSE", "UPSTREAM.md"]


def hook_definition(target: Path, node: Path) -> dict:
    node_path = node.as_posix()
    script = (target / "codex.mjs").as_posix()
    hook = {"type": "command", "command": f"{shlex.quote(node_path)} {shlex.quote(script)}",
        "timeout": 20, "statusMessage": "Jev Belay: checking completion evidence (shadow)"}
    if os.name == "nt":
        # Keep paths literal through both cmd.exe and PowerShell.
        quoted_node = node_path.replace("'", "''")
        quoted_script = script.replace("'", "''")
        wrapper = (
            "$ProgressPreference = 'SilentlyContinue'; $utf8 = [System.Text.UTF8Encoding]::new($false); "
            "[Console]::InputEncoding = $utf8; [Console]::OutputEncoding = $utf8; $OutputEncoding = $utf8; "
            f"& '{quoted_node}' '{quoted_script}'; exit $LASTEXITCODE"
        )
        encoded = base64.b64encode(wrapper.encode("utf-16le")).decode("ascii")
        hook["commandWindows"] = f"powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand {encoded}"
    return {"hooks": [hook]}


def install(root: Path, node: Path, env_file: Path, allow_prompt_export: bool = False) -> dict:
    root = root.resolve()
    target = root / "belay"
    hook_file = root / "hooks.json"
    for path in [root, target, hook_file, *[target / name for name in FILES], target / "config.json"]:
        if path.is_symlink():
            raise ValueError(f"Refusing symlinked destination: {path}")
    config = json.loads(hook_file.read_text(encoding="utf-8-sig")) if hook_file.exists() else {}
    if not isinstance(config, dict) or not isinstance(config.get("hooks", {}), dict):
        raise ValueError("Invalid existing hooks configuration")
    definition = hook_definition(target, node)
    groups = config.setdefault("hooks", {}).setdefault("Stop", [])
    script = target / "codex.mjs"
    script_forms = (str(script), script.as_posix(), shlex.quote(script.as_posix()))
    matches = [g for g in groups if any(any(path in h.get("command", "") for path in script_forms) for h in g.get("hooks", []))]
    if len(matches) > 1 or matches and matches[0] != definition:
        raise ValueError("Conflicting Jev Belay registration; review before replacement")
    for name in FILES:
        dest = target / name
        if dest.exists() and dest.read_bytes() != (SOURCE / name).read_bytes():
            raise ValueError(f"Installed file differs; review before replacement: {dest}")
    settings = {"threshold": 0.75, "log": True, "shadow": True, "model": "jev-1.14.0", "env_file": str(env_file.resolve()),
        "allow_prompt_export": allow_prompt_export}
    if (target / "config.json").exists() and json.loads((target / "config.json").read_text(encoding="utf-8-sig")) != settings:
        raise ValueError("Installed settings differ; review before replacement")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target.mkdir(parents=True, mode=0o700, exist_ok=True)
    hashes = {}
    for name in FILES:
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / name, dest)
        hashes[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    settings_file = target / "config.json"
    settings_file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    settings_file.chmod(0o600)
    backup = None
    if not matches:
        if hook_file.exists():
            backup = target / f"hooks.before-{stamp}.json"
            shutil.copy2(hook_file, backup)
            backup.chmod(0o600)
        groups.append(definition)
        temporary = root / "hooks.json.jev-belay.tmp"
        temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(hook_file)
    manifest = {"installed_at": stamp, "upstream_version": "0.2.0", "upstream_commit": COMMIT,
        "files_sha256": hashes, "hook_file": str(hook_file), "backup": str(backup) if backup else None,
        "settings": settings, "node": str(node)}
    (target / "installation.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"installed": True, "directory": str(target), "hook": definition, "settings": settings,
        "backup": manifest["backup"], "trust_review_required": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    parser.add_argument("--node", type=Path, default=Path(shutil.which("node") or "/opt/homebrew/bin/node"))
    parser.add_argument("--env-file", type=Path, default=Path.home() / ".config/typesafe/env")
    parser.add_argument("--allow-prompt-export", action="store_true", help="Explicitly allow redacted task/final/check summaries to TypeSafe")
    args = parser.parse_args()
    print(json.dumps(install(args.codex_home, args.node, args.env_file, args.allow_prompt_export), indent=2))
