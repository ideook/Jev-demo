import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "scripts" / "install_jev_explore.py"


class ExploreInstallTests(unittest.TestCase):
    def test_removing_only_hook_keeps_following_native_trust_indexes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as tmp:
            home = Path(tmp)
            self.assertEqual(self.run_install(home).returncode, 0)
            script = (home / "skills/jev-explore/scripts/jev_explore_hook.py").as_posix()
            owned = {"type": "command", "command": f'python3 -X utf8 "{script}"', "timeout": 5}
            following = {"hooks": [{"type": "command", "command": "python north_star.py"}]}
            config = {"hooks": {"PostToolUse": [{"matcher": "^Bash$", "hooks": [owned]}, following]}}
            (home / "hooks.json").write_text(json.dumps(config), encoding="utf-8")
            result = self.run_install(home)
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads((home / "hooks.json").read_bytes())
            self.assertEqual(actual["hooks"]["PostToolUse"], [{"matcher": "^Bash$", "hooks": []}, following])

    def run_install(self, home, *options):
        return subprocess.run(
            [sys.executable, str(INSTALLER), "--codex-home", str(home), *options],
            env=os.environ | {"CODEX_HOME": str(home)}, capture_output=True,
            text=True, encoding="utf-8", timeout=30,
        )

    def test_fresh_install_has_no_shell_hook_and_is_idempotent(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as tmp:
            home = Path(tmp)
            first = self.run_install(home)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertFalse((home / "hooks.json").exists())
            self.assertTrue((home / "skills/jev-explore/scripts/jev_rank.py").is_file())
            self.assertEqual(self.run_install(home).returncode, 0)

    def test_update_removes_only_owned_legacy_hook_and_backs_up_changes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as tmp:
            home = Path(tmp) / "한글 user's Codex"
            skill = home / "skills/jev-explore"
            shutil.copytree(ROOT / "skills/jev-explore", skill)
            (skill / "SKILL.md").write_text("old custom version", encoding="utf-8")
            owned = {"type": "command", "command": f'"{sys.executable}" "{(skill / "scripts/jev_explore_hook.py").as_posix()}"',
                     "commandWindows": "powershell.exe -EncodedCommand LEGACY", "timeout": 5}
            unrelated = {"type": "command", "command": "python north_star.py", "timeout": 12}
            config = {"version": 1, "hooks": {"PostToolUse": [{"matcher": "^Bash$", "disabled": False,
                        "hooks": [owned, unrelated]}], "Stop": [{"hooks": [unrelated]}]}}
            original = json.dumps(config, ensure_ascii=False).encode("utf-8")
            (home / "hooks.json").write_bytes(original)
            mixed_group = self.run_install(home, "--update")
            self.assertNotEqual(mixed_group.returncode, 0)
            self.assertEqual((home / "hooks.json").read_bytes(), original)
            self.assertEqual((skill / "SKILL.md").read_text(encoding="utf-8"), "old custom version")
            config["hooks"]["PostToolUse"] = [{"matcher": "^Bash$", "hooks": [owned]},
                                               {"matcher": "^Bash$", "disabled": False, "hooks": [unrelated]}]
            original = json.dumps(config, ensure_ascii=False).encode("utf-8")
            (home / "hooks.json").write_bytes(original)
            rejected = self.run_install(home)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual((home / "hooks.json").read_bytes(), original)
            installed = self.run_install(home, "--update")
            self.assertEqual(installed.returncode, 0, installed.stderr)
            receipt = json.loads(installed.stdout)
            updated = json.loads((home / "hooks.json").read_text(encoding="utf-8"))
            expected = json.loads(original)
            expected["hooks"]["PostToolUse"][0]["hooks"] = []
            self.assertEqual(updated, expected)
            backup = Path(receipt["backup_path"])
            self.assertEqual((backup / "hooks.json").read_bytes(), original)
            self.assertEqual((backup / "skills/jev-explore/SKILL.md").read_text(encoding="utf-8"), "old custom version")
            after = (home / "hooks.json").read_bytes()
            self.assertEqual(self.run_install(home).returncode, 0)
            self.assertEqual((home / "hooks.json").read_bytes(), after)

    def test_invalid_config_is_rejected_before_skill_files_change(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as tmp:
            home = Path(tmp)
            (home / "hooks.json").write_text('{"hooks": {"PostToolUse": "bad"}}')
            result = self.run_install(home, "--update")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((home / "skills").exists())


if __name__ == "__main__":
    unittest.main()
