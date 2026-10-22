import importlib.util
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "jev-explore" / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rank = load("jev_rank")
hook = load("jev_explore_hook")
rank.CACHE_ROOT = ROOT / ".cache" / "jev-explore-unit-cache"
hook.CACHE_ROOT = rank.CACHE_ROOT
(ROOT / ".cache").mkdir(exist_ok=True)


def candidate(path="feature.py"):
    return {"path": path, "line": 1, "excerpt": "1 | def employee_pay(): return 42", "excerpt_truncated": False, "size": 34, "mtime_ns": 0}


def answer(score=3, confidence=1):
    return {"model": "jev-test", "answers": {"file_0": {"type": "score", "score": score, "confidence": confidence, "probabilities": {str(i): 1 if i == score else 0 for i in range(4)}}}}


class ExploreTests(unittest.TestCase):
    def test_dry_run_with_unicode_space_and_quote_paths_needs_no_hook_or_credentials(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as tmp:
            root = Path(tmp) / "한글 user's source"
            root.mkdir()
            (root / "급여.py").write_text("def employee_pay(): return 42\n", encoding="utf-8")
            result = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "jev_rank.py"),
                "Where is employee pay?", "--root", str(root), "--keyword", "employee_pay", "--dry-run"],
                capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("급여.py:1", result.stdout)
            self.assertIn("0 API calls", result.stdout)
            self.assertIn("Lexical suggestions only", result.stdout)
            cached = Path(result.stdout.split("JEV_EXPLORE_RESULT=", 1)[1].strip())
            self.assertFalse(cached.with_suffix(".hook.json").exists())
            cached.unlink()

    def test_changed_files_and_capped_discovery_remain_visible_in_direct_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as tmp:
            root = Path(tmp)
            source = root / "feature.py"
            source.write_text("employee_pay = 42\n")
            row = candidate() | {"score": 1, "confidence": 1, "size": source.stat().st_size,
                                 "mtime_ns": source.stat().st_mtime_ns}
            report = {"status": "ok", "root": str(root), "candidate_count": 1, "api_calls": 1,
                      "elapsed_ms": 0, "top": 5, "ranked": [row], "lexical_suggestions": [], "shortlist_truncated": True}
            source.write_text("changed after ranking\n")
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                rank.display(report, root / "report.json")
            self.assertIn("changed after evaluation", stdout.getvalue())
            self.assertIn("Candidate discovery was capped", stdout.getvalue())
            self.assertNotIn("feature.py:1", stdout.getvalue())

    def test_rank_command_delivers_reading_context_without_a_hook_or_extra_api(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as tmp:
            root = Path(tmp).resolve()
            (root / "feature.py").write_text("def employee_pay(): return 42\n")
            argv = ["jev_rank.py", "Where is employee pay implemented?", "--root", str(root), "--keyword", "employee_pay"]
            with patch.object(rank.sys, "argv", argv), patch.object(rank, "credential", return_value="synthetic-key"), \
                    patch.object(rank.urllib.request, "urlopen") as api, contextlib.redirect_stdout(io.StringIO()) as stdout:
                api.return_value.__enter__.return_value.read.return_value = json.dumps(answer()).encode()
                self.assertEqual(rank.main(), 0)
            self.assertEqual(api.call_count, 1)
            output = stdout.getvalue()
            self.assertIn("feature.py:1", output)
            self.assertIn("Read the listed source files first", output)
            marker = output.split("JEV_EXPLORE_RESULT=", 1)[1].strip()
            cached = Path(marker)
            self.assertTrue(cached.is_file())
            self.assertFalse(cached.with_suffix(".hook.json").exists())
            cached.unlink()

    def test_local_search_excludes_credentials_vendor_and_external_symlinks(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as tmp:
            root = Path(tmp).resolve()
            (root / "feature.py").write_text('JEV_API_KEY = "do-not-transmit"\ndef employee_pay(): return 42\n')
            (root / ".env").write_text("JEV_API_KEY=do-not-read")
            (root / "credentials.py").write_text("employee_pay = 'secret'")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "feature.py").write_text("employee_pay = 42")
            candidates, _ = rank.shortlist(root, ["employee_pay"], 100, 5000)
            self.assertEqual([item["path"] for item in candidates], ["feature.py"])
            self.assertNotIn("do-not-transmit", candidates[0]["excerpt"])
            self.assertIn("[REDACTED]", candidates[0]["excerpt"])
            self.assertIsNone(rank.safe_source(root, "../outside.py"))
            self.assertIsNone(rank.safe_source(root, "credentials.py"))

    def test_snippet_contains_far_away_match_with_line_anchor(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as tmp:
            root = Path(tmp).resolve()
            (root / "module.py").write_text("\n" * 300 + "def employee_pay(): return 42\n")
            candidates, _ = rank.shortlist(root, ["employee_pay"], 100, 5000)
            self.assertIn("301 | def employee_pay", candidates[0]["excerpt"])
            self.assertEqual(candidates[0]["line"], 301)

    def test_ignored_files_remain_ignored(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as tmp:
            root = Path(tmp).resolve()
            (root / ".git").mkdir()
            (root / ".gitignore").write_text("ignored.py\n")
            (root / "ignored.py").write_text("employee_pay = 42")
            (root / "feature.py").write_text("employee_pay = 42")
            candidates, _ = rank.shortlist(root, ["employee_pay"], 100, 5000)
            self.assertEqual([item["path"] for item in candidates], ["feature.py"])

    def test_batches_follow_bytes_and_optional_count_not_twenty(self):
        items = [candidate(f"f{i}.py") for i in range(35)]
        byte_budget = len(json.dumps(rank.request_for("pay", items[:7], "jev-1.14.0"), ensure_ascii=False).encode("utf-8"))
        batches = rank.pack_batches("pay", items, "jev-1.14.0", byte_budget, None)
        self.assertEqual(sum(map(len, batches)), 35)
        self.assertTrue(all(len(batch) <= 7 for batch in batches))
        counted = rank.pack_batches("pay", items, "jev-1.14.0", 200000, 11)
        self.assertEqual(list(map(len, counted)), [11, 11, 11, 2])
        self.assertEqual(len(rank.pack_batches("pay", items, "jev-1.14.0", 200000, None)), 1)

    def test_scores_normalized_and_invalid_responses_rejected(self):
        self.assertEqual(rank.parse_answers(answer(), [candidate()])[0]["score"], 1)
        for bad in ([], {"answers": {}}, answer(score=True), answer(confidence=float("nan"))):
            with self.assertRaises(rank.ExploreError):
                rank.parse_answers(bad, [candidate()])
        bad = answer()
        bad["answers"]["file_0"]["probabilities"]["3"] = 0.1
        with self.assertRaises(rank.ExploreError):
            rank.parse_answers(bad, [candidate()])

    def test_api_failure_is_not_a_score_and_hides_response_body(self):
        with patch.object(rank.urllib.request, "urlopen", side_effect=urllib.error.HTTPError("url", 401, "secret-value", {}, None)):
            result = rank.evaluate_batch("pay", [candidate()], "secret-value", "jev-1.14.0", 1)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("rows", result)
        self.assertNotIn("secret-value", json.dumps(result))
        self.assertEqual(result["attempts"], 1)

    def test_rate_limit_retry_is_bounded(self):
        with patch.object(rank.urllib.request, "urlopen", side_effect=urllib.error.HTTPError("url", 429, "rate", {}, None)) as api, patch.object(rank.time, "sleep"):
            result = rank.evaluate_batch("pay", [candidate()], "secret", "jev-1.14.0", 1)
        self.assertEqual(api.call_count, 2)
        self.assertEqual(result["status"], "failed")

    def test_hook_context_no_extra_api_and_rejects_wrong_root_or_stale_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as tmp:
            root = Path(tmp).resolve()
            source = root / "feature.py"
            source.write_text("def employee_pay(): return 42\n")
            stat = source.stat()
            report = {"schema": rank.SCHEMA, "root": str(root), "status": "ok", "candidate_count": 1, "top": 5, "ranked": [candidate() | {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "score": 1}]}
            cached = rank.write_report(report, None)
            event = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": 'python "C:/skills/jev-explore/scripts/jev_rank.py" "pay"'}, "tool_response": {"output": f"summary\nJEV_EXPLORE_RESULT={cached}\n"}, "cwd": str(root), "_test_event": True}
            try:
                with patch.object(rank.urllib.request, "urlopen") as api:
                    output = hook.feedback(event)
                api.assert_not_called()
                self.assertIn("feature.py", output["hookSpecificOutput"]["additionalContext"])
                self.assertEqual(hook.feedback(event | {"cwd": str(root.parent)}), {})
                self.assertEqual(hook.feedback(event | {"tool_input": {"command": "rg pay"}}), {})
                source.write_text("changed\n")
                self.assertIn("changed after evaluation", hook.feedback(event)["hookSpecificOutput"]["additionalContext"])
            finally:
                cached.unlink(missing_ok=True)
                cached.with_suffix(".hook.json").unlink(missing_ok=True)

    def test_credential_parser_reads_named_values_without_shell_evaluation(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as tmp:
            root = Path(tmp)
            (root / ".env").write_text('OTHER_KEY=ignored\nJEV_API_KEY="literal-$(command)"\n')
            with patch.dict(rank.os.environ, {}, clear=True):
                self.assertEqual(rank.credential(root, None), "literal-$(command)")

    def test_user_environment_fallback_without_process_key_or_dotenv(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as tmp:
            with patch.dict(rank.os.environ, {}, clear=True), patch.object(rank, "windows_user_credential", return_value="shared-key") as user_key:
                self.assertEqual(rank.credential(Path(tmp), None), "shared-key")
            user_key.assert_called_once_with(("JEV_API_KEY", "TYPESAFE_API_KEY"))

    def test_process_key_takes_priority_over_user_environment(self):
        with patch.dict(rank.os.environ, {"JEV_API_KEY": "process-key"}, clear=True), patch.object(rank, "windows_user_credential") as user_key:
            self.assertEqual(rank.credential(ROOT, None), "process-key")
        user_key.assert_not_called()


if __name__ == "__main__":
    unittest.main()
