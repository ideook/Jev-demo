import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("jev_commit_observer", REPO / "experiments/jev-commit-observer/observer.py")
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)
RUNTIME = REPO / ".runtime/experiments/jev-commit-observer-tests"


def run_git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def good_answer():
    return {"complete": .99, "cohesive": .99, "message_matches": .99, "pending_related": .01}, {"model": observer.MODEL, "usage": {}, "latency_ms": 1}


class ObserverTests(unittest.TestCase):
    def setUp(self):
        RUNTIME.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=RUNTIME)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        run_git(self.root, "init", "-q")
        (self.root / ".gitignore").write_text(".runtime/\n__pycache__/\n.env\n", encoding="utf-8")
        (self.root / "feature.py").write_text("value = 1\n", encoding="utf-8")
        run_git(self.root, "add", ".gitignore", "feature.py")
        run_git(self.root, "-c", "user.name=Observer Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + str(self.root / "no-hooks"), "commit", "-qm", "fixture baseline")
        self.plan = {"title": "Update value", "message": "fix: update value to two", "acceptance": ["value is two"],
                     "files": ["feature.py"], "checks": [["{python}", "-B", "-c", "import feature; assert feature.value == 2"]]}
        self.path = observer.session_path(self.root, "unit")

    def start(self):
        observer.begin(self.root, self.path, self.plan)
        (self.root / "feature.py").write_text("value = 2\n", encoding="utf-8")
        state = observer.read_state(self.root, self.path)
        observer.verify(self.root, self.path, state)
        return state

    def observe_live(self, state, answer=None):
        with patch.object(observer, "credential", return_value="test-key"), patch.object(observer, "ask", return_value=answer or good_answer()) as api:
            result = observer.observe(self.root, self.path, state, True, True)
        return result, api

    def test_ready_recommendation_preserves_head_index_and_worktree(self):
        state = self.start()
        before = observer.snapshot(self.root)
        index = (self.root / ".git/index").read_bytes()
        result, api = self.observe_live(state)
        self.assertEqual(result["decision"], "would_commit")
        self.assertEqual(result["candidate_files"], ["feature.py"])
        self.assertFalse(result["commit_created"])
        self.assertEqual(observer.snapshot(self.root), before)
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(state["calls"], 1)

    def test_no_api_without_both_live_and_export_flags(self):
        state = self.start()
        with patch.object(observer, "ask") as api:
            offline = observer.observe(self.root, self.path, state)
            unapproved = observer.observe(self.root, self.path, state, True, False)
        api.assert_not_called()
        self.assertEqual(offline["decision"], "awaiting_judgment")
        self.assertIn("diff_export_not_allowed", unapproved["reasons"])

    def test_repeated_checks_of_same_tree_do_not_repeat_paid_call(self):
        state = self.start()
        self.observe_live(state)
        observer.verify(self.root, self.path, state)
        result, api = self.observe_live(state)
        api.assert_not_called()
        self.assertTrue(result["cached"])
        self.assertEqual(state["calls"], 1)

    def test_failed_or_stale_checks_never_recommend_commit(self):
        state = self.start()
        (self.root / "feature.py").write_text("value = 3\n", encoding="utf-8")
        result, api = self.observe_live(state)
        api.assert_not_called()
        self.assertIn("missing_failed_or_stale_verification", result["reasons"])
        observer.verify(self.root, self.path, state)
        result, api = self.observe_live(state)
        api.assert_not_called()
        self.assertEqual(state["verification"]["checks"][0]["status"], "failed")
        self.assertEqual(result["decision"], "hold")

    def test_preexisting_changes_and_staging_are_not_exported_or_altered(self):
        (self.root / "feature.py").write_text("value = 4\n", encoding="utf-8")
        run_git(self.root, "add", "feature.py")
        state = self.start()
        before = observer.snapshot(self.root)
        result, api = self.observe_live(state)
        api.assert_not_called()
        self.assertIn("preexisting_changes", result["reasons"])
        self.assertIn("existing_staging", result["reasons"])
        self.assertEqual(observer.snapshot(self.root), before)

    def test_unrelated_new_file_blocks_even_after_successful_checks(self):
        state = self.start()
        (self.root / "other.py").write_text("other = 1\n", encoding="utf-8")
        observer.verify(self.root, self.path, state)
        result, api = self.observe_live(state)
        api.assert_not_called()
        self.assertIn("unrelated_files_in_worktree", result["reasons"])
        self.assertEqual(result["excluded_files"], ["other.py"])

    def test_check_that_changes_source_invalidates_its_own_evidence(self):
        self.plan["checks"] = [["{python}", "-c", "from pathlib import Path; Path('feature.py').write_text('value = 9\\n')"]]
        state = self.start()
        result, api = self.observe_live(state)
        api.assert_not_called()
        self.assertFalse(state["verification"]["unchanged"])
        self.assertEqual(result["decision"], "hold")

    def test_error_and_call_budget_are_holds_not_success(self):
        state = self.start()
        with patch.object(observer, "credential", return_value="never-log-me"), patch.object(observer, "ask", side_effect=observer.ObserverError("api_transport_failed")) as api:
            first = observer.observe(self.root, self.path, state, True, True)
            second = observer.observe(self.root, self.path, state, True, True)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(first["decision"], "hold")
        self.assertTrue(second["cached"])
        self.assertNotIn("never-log-me", self.path.read_text())
        self.assertEqual(state["calls"], 1)
        state["last"] = None
        state["calls"] = observer.MAX_CALLS
        result, api = self.observe_live(state)
        api.assert_not_called()
        self.assertIn("session_call_budget_exhausted", result["reasons"])

    def test_state_change_while_model_is_running_discards_recommendation(self):
        state = self.start()
        def change(*args):
            (self.root / "feature.py").write_text("value = 5\n", encoding="utf-8")
            return good_answer()
        with patch.object(observer, "credential", return_value="test-key"), patch.object(observer, "ask", side_effect=change):
            result = observer.observe(self.root, self.path, state, True, True)
        self.assertEqual(result["decision"], "hold")
        self.assertIn("worktree_changed_during_observation", result["reasons"])

    def test_semantic_failure_and_uncertainty_hold(self):
        state = self.start()
        for name, value in (("complete", .5), ("cohesive", .2), ("message_matches", .6), ("pending_related", .7)):
            state["last"] = None
            answers, metrics = good_answer()
            answers[name] = value
            result, _ = self.observe_live(state, (answers, metrics))
            self.assertEqual(result["decision"], "hold")

    def test_secret_like_added_content_is_never_sent_or_logged(self):
        self.plan["checks"] = [["{python}", "-c", "pass"]]
        state = self.start()
        secret = "invented" + "-credential-value"
        (self.root / "feature.py").write_text('api_key = "' + secret + '"\n', encoding="utf-8")
        observer.verify(self.root, self.path, state)
        result, api = self.observe_live(state)
        api.assert_not_called()
        self.assertIn("secret_like_content_not_exported", result["reasons"])
        self.assertNotIn(secret, self.path.with_name("observations.jsonl").read_text())

    def test_oversize_and_binary_are_not_silently_clipped(self):
        self.plan["checks"] = [["{python}", "-c", "pass"]]
        state = self.start()
        for data in (b"x" * (observer.MAX_FILE + 1), b"abc\x00def"):
            (self.root / "feature.py").write_bytes(data)
            observer.verify(self.root, self.path, state)
            result, api = self.observe_live(state)
            api.assert_not_called()
            self.assertIn("oversize_or_binary_candidate", result["reasons"])

    def test_model_schema_rejects_bool_nan_missing_and_wrong_type(self):
        response = {"answers": {k: {"type": "noul", "noul": .5} for k in observer.QUESTIONS}}
        self.assertEqual(len(observer.parse_answer(response)), 4)
        for v in (True, math.nan, 1.1, "0.9"):
            response["answers"]["complete"]["noul"] = v
            with self.assertRaises(observer.ObserverError):
                observer.parse_answer(response)
        with self.assertRaises(observer.ObserverError):
            observer.parse_answer({"answers": {}})
        for bad in ([], {"answers": []}, {"answers": {"complete": []}}):
            with self.assertRaises(observer.ObserverError):
                observer.parse_answer(bad)

    def test_known_opaque_authentication_key_cannot_appear_in_api_state(self):
        self.plan["checks"] = [["{python}", "-c", "pass"]]
        state = self.start()
        key = "opaque" + "-known-auth-value"
        (self.root / "feature.py").write_text('other = "' + key + '"\n', encoding="utf-8")
        observer.verify(self.root, self.path, state)
        with patch.object(observer, "credential", return_value=key), patch.object(observer, "ask") as api:
            result = observer.observe(self.root, self.path, state, True, True)
        api.assert_not_called()
        self.assertIn("configured_credential_not_exported", result["reasons"])
        self.assertNotIn(key, self.path.with_name("observations.jsonl").read_text())

    def test_cli_begin_check_and_review_work_without_paid_api(self):
        self.plan["title"] = "한글 작업 단위"
        plan_path = self.root / ".runtime/plan.json"
        plan_path.parent.mkdir(parents=True)
        plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        def cli(action, *extra):
            result = subprocess.run([sys.executable, str(REPO / "experiments/jev-commit-observer/observer.py"), action,
                                     "--root", str(self.root), "--session", "cli", *extra], capture_output=True, text=True,
                                    encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "ascii"})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)
        cli("begin", "--plan", str(plan_path))
        (self.root / "feature.py").write_text("value = 2\n", encoding="utf-8")
        report = cli("check")
        self.assertEqual(report["decision"], "awaiting_judgment")
        self.assertEqual(report["unit"], "한글 작업 단위")
        self.assertFalse(report["api_attempted"])
        self.assertEqual(cli("review", "--label", "unsure")["labeled"], 1)

    def test_path_and_command_policy_is_portable_and_explicit(self):
        for name in ("../outside.py", "/etc/passwd", "C:/outside.py", "a\\b.py"):
            with self.assertRaises(observer.ObserverError):
                observer.safe_path(name)
        for name in (".env", "a/credentials.json", "node_modules/a.js", "private.key"):
            self.assertTrue(observer.excluded(name))
        for cmd in (["git", "commit"], ["powershell", "do-something"], "python test.py"):
            with self.assertRaises(observer.ObserverError):
                observer.validate_plan({**self.plan, "checks": [cmd]})
        self.assertEqual(observer.validate_plan(self.plan), self.plan)

    def test_credential_env_file_is_data_not_shell_code(self):
        home = self.root / "fake-home"
        env = home / ".config/typesafe/env"
        env.parent.mkdir(parents=True)
        env.write_text('export TYPESAFE_API_KEY="literal-$(do-not-run)"\n', encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True), patch.object(observer.Path, "home", return_value=home):
            self.assertEqual(observer.credential(), "literal-$(do-not-run)")

    def test_session_lock_and_human_labels(self):
        state = self.start()
        with observer.locked(self.path):
            with self.assertRaises(observer.ObserverError):
                with observer.locked(self.path):
                    pass
        self.observe_live(state)
        result = observer.review(self.path, "accept")
        self.assertEqual(result["labeled"], 1)
        self.assertTrue(result["comparisons"][0]["agrees"])
        with self.assertRaises(observer.ObserverError):
            observer.begin(self.root, self.path, self.plan)


if __name__ == "__main__":
    unittest.main()
