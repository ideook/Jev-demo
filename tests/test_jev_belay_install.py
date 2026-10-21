"""Offline Belay installation and platform command checks."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("install_belay", ROOT / "scripts/install_jev_belay.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class BelayInstallationTests(unittest.TestCase):
    def test_reinstall_preserves_other_hooks_and_does_not_add_a_second_stop_hook(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "한글 user's home"
            root.mkdir()
            original = {"description": "기존 훅", "hooks": {"PostToolUse": [{"hooks": [{"command": "existing"}]}]}}
            hook_file = root / "hooks.json"
            hook_file.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8-sig")
            node = Path(shutil.which("node") or "/usr/bin/node")
            installer.install(root, node, root / "private.env")
            first = hook_file.read_bytes()
            installer.install(root, node, root / "private.env")
            self.assertEqual(hook_file.read_bytes(), first)
            config = json.loads(first)
            self.assertEqual(config["hooks"]["PostToolUse"], original["hooks"]["PostToolUse"])
            self.assertEqual(len(config["hooks"]["Stop"]), 1)
            self.assertEqual(len(list((root / "belay").glob("hooks.before-*.json"))), 1)
            hook = config["hooks"]["Stop"][0]["hooks"][0]
            self.assertEqual(shlex.split(hook["command"]), [node.as_posix(), (root / "belay/codex.mjs").as_posix()])
            self.assertFalse(json.loads((root / "belay/config.json").read_text(encoding="utf-8"))["allow_prompt_export"])

    def test_conflicting_hook_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = {"hooks": {"Stop": [{"hooks": [{"command": f'node "{(root / "belay/codex.mjs").as_posix()}"', "timeout": 99}]}]}}
            hook_file = root / "hooks.json"
            hook_file.write_text(json.dumps(original), encoding="utf-8")
            first = hook_file.read_bytes()
            with self.assertRaises(ValueError):
                installer.install(root, Path("node"), root / "private.env")
            self.assertEqual(hook_file.read_bytes(), first)

    @unittest.skipUnless(os.name == "nt" and shutil.which("node"), "Windows with Node")
    def test_registered_windows_command_runs_node_with_utf8_pipes(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "한글 user's space"
            target.mkdir()
            (target / "codex.mjs").write_text(
                'import { readFileSync } from "node:fs"; console.log(JSON.stringify(JSON.parse(readFileSync(0, "utf8"))));\n',
                encoding="utf-8")
            command = installer.hook_definition(target, Path(shutil.which("node")))["hooks"][0]["commandWindows"]
            event = {"prompt": "한글 입력", "cwd": str(target)}
            result = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command],
                input=json.dumps(event, ensure_ascii=False), text=True, capture_output=True, encoding="utf-8", timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), event)
            self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
