"""Meaningful contract checks; API responses here are deliberately mocked."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "hooks" / "jev-hook-demo"
spec = importlib.util.spec_from_file_location("jev_hook", DEMO / "jev_judge_hook.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


def event(path="hooks/jev-hook-demo/access_control.py", cwd=ROOT):
    return {
        "hook_event_name": "PostToolUse", "tool_name": "apply_patch", "cwd": str(cwd),
        "tool_input": {"command": f"*** Begin Patch\n*** Update File: {path}\n@@\n-old\n+new\n*** End Patch"},
    }


class HookContractTests(unittest.TestCase):
    def test_only_demo_edits_are_selected(self):
        self.assertEqual(hook.scoped_changes(event()), ["access_control.py"])
        self.assertEqual(hook.scoped_changes(event(".env")), [])
        self.assertEqual(hook.scoped_changes(event(cwd=ROOT.parent)), [])
        self.assertEqual(hook.scoped_changes(event("../../secrets.txt")), [])

    def test_wrong_event_and_tool_are_ignored(self):
        data = event()
        data["hook_event_name"] = "PreToolUse"
        self.assertEqual(hook.scoped_changes(data), [])
        data["hook_event_name"] = "PostToolUse"
        data["tool_name"] = "Bash"
        self.assertEqual(hook.scoped_changes(data), [])

    def test_questions_contain_rule_meaning_not_only_ids(self):
        request, rules = hook.build_request()
        self.assertEqual(len(rules), 4)
        self.assertEqual(set(request["state"]), set(hook.WATCHED_FILES))
        for rule_id, rule in rules.items():
            self.assertIn(rule, request["questions"][rule_id]["instructions"])

    def test_missing_key_is_not_reported_as_success(self):
        with patch.object(hook, "local_settings", return_value={"provider": "typesafe"}), patch.object(hook, "api_key", return_value=None), patch.object(hook, "call_jev") as api:
            result = hook.evaluate(["access_control.py"])
        self.assertEqual(result["status"], "missing_api_key")
        self.assertFalse(result["api_called"])
        api.assert_not_called()

    def test_missing_provider_prevents_credential_transmission(self):
        with patch.object(hook, "local_settings", return_value={"provider": "unconfigured"}), patch.object(hook, "call_jev") as api:
            self.assertEqual(hook.evaluate([])["status"], "missing_provider")
        api.assert_not_called()

    def test_report_preserves_uncertain_answers(self):
        rules = {"A": "Rule A", "B": "Rule B", "C": "Rule C"}
        response = {"answers": {k: {"type": "noul", "noul": p} for k, p in zip(rules, [0.99, 0.02, 0.5])}}
        rows = hook.summarize(response, rules)
        self.assertEqual([r["status"] for r in rows], ["covered", "missing", "review"])
        context = hook.hook_output({"status": "ok", "rules": rows})["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Add meaningful tests", context)
        self.assertIn("uncertain", context)

    def test_incomplete_and_invalid_answers_are_rejected(self):
        rules = {"A": "Rule A"}
        for response in ({"answers": {}}, {"answers": {"A": {"type": "noul", "noul": True}}}, {"answers": {"A": {"type": "noul", "noul": float("nan")}}}):
            with self.assertRaises(ValueError):
                hook.summarize(response, rules)


if __name__ == "__main__":
    unittest.main()
