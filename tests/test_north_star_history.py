"""Historical evaluation contracts use synthetic transcripts and fake providers."""
import contextlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "experiments/north-star" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


history = load("history_replay")
limits = load("replay_history_limits")
runner = load("run_history_cases")
policy_replay = load("replay_policy")


def message(text, stamp, role="user", phase=None):
    return {"type": "response_item", "timestamp": stamp,
            "payload": {"type": "message", "role": role, "phase": phase, "content": text}}


class HistoryEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sid = "history-test-00001"
        self.sessions = self.root / "sessions"
        self.sessions.mkdir()
        self.output = self.root / "inventory"
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for module in (history, limits, runner):
            self.stack.enter_context(patch.object(module.ns, "credentials", return_value="fake-secret"))
        self.provider = self.stack.enter_context(patch.object(runner.ns, "ask"))

    def transcript(self, records, name="a"):
        path = self.sessions / f"{name}-{self.sid}.jsonl"
        meta = {"type": "session_meta", "payload": {"id": self.sid, "source": "vscode"}}
        path.write_text("".join(json.dumps(r) + "\n" for r in [meta, *records]))
        return path

    def inventory(self):
        return history.inventory(self.sid, self.sessions, self.output)

    def cases(self, text="Synthetic input"):
        path = self.root / "cases.json"
        path.write_text(json.dumps([{"id": "one", "cohort": "synthetic",
                                    "view": {"current": text}, "expected_actions": ["silent"]}]))
        return path

    def test_originals_only_and_repeated_requests_survive(self):
        original = message("Try again", "1")
        self.transcript([original,
                         {"type": "event_msg", "timestamp": "1",
                          "payload": {"type": "user_message", "message": "Try again"}},
                         message("Try again", "2"),
                         message("hidden reasoning", "3", "assistant", "analysis"),
                         {"type": "response_item", "payload": {"type": "function_call_output", "output": "secret"}},
                         message("Done", "4", "assistant", "final_answer")])
        self.transcript([original], "b")
        result = self.inventory()
        self.assertEqual((result["users"], result["messages"], result["finals"]), (2, 3, 1))

    def test_mismatched_thread_is_rejected(self):
        path = self.transcript([])
        path.write_text(json.dumps({"type": "session_meta", "payload": {"id": "another-thread"}}) + "\n")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.inventory()

    def test_existing_snapshot_is_preserved(self):
        self.transcript([message("Keep this", "1")])
        self.inventory()
        before = (self.output / "messages.json").read_bytes()
        with self.assertRaises(ValueError):
            self.inventory()
        self.assertEqual(before, (self.output / "messages.json").read_bytes())

    def test_empty_source_does_not_report_success(self):
        with self.assertRaisesRegex(ValueError, "No matching"):
            self.inventory()

    def test_incomplete_record_is_not_a_message(self):
        path = self.transcript([message("Complete", "1")])
        with path.open("ab") as stream:
            stream.write(b'{"type":"response_item"')
        result = self.inventory()
        self.assertEqual(result["messages"], 1)
        self.assertEqual(result["files"][0]["counts"]["incomplete_records"], 1)

    def test_recent_cap_dominates_current_cap(self):
        self.assertTrue(limits.assess("x" * 1200, [{"text": "x" * 1200}])["text_caps_pass"])
        result = limits.assess("x" * 1201, [{"text": "x" * 1201}])
        self.assertEqual(result["blockers"], ["recent_over_1200"])
        self.assertFalse(result["text_caps_pass"])

    def test_citation_sensitivity_does_not_change_actual_gate(self):
        text = "Short answer.\n<oai-mem-citation>" + "x" * 1300
        result = limits.assess(text, [{"text": text}])
        self.assertFalse(result["text_caps_pass"])
        self.assertTrue(result["without_citation_caps_pass"])

    def test_current_policy_removes_exact_duplicate_without_discarding_old_conditions(self):
        text = "가" * 1500
        tail = [{"role": "user", "text": "설명해줘"}, {"role": "assistant", "text": text}]
        self.assertFalse(limits.assess(text, tail)["text_caps_pass"])
        self.assertTrue(limits.assess_current(text, tail, "assistant")["text_caps_pass"])
        tail.insert(0, {"role": "assistant", "text": "중요한 조건 " * 300})
        self.assertFalse(limits.assess_current(text, tail, "assistant")["text_caps_pass"])

    def test_future_long_message_cannot_contaminate_earlier_final(self):
        self.transcript([message("Request", "1"),
                         message("Short result", "2", "assistant", "final_answer"),
                         message("x" * 2001, "3", "assistant", "final_answer")])
        self.inventory()
        output = self.root / "limits.json"
        limits.replay(self.output / "inventory.json", self.output / "messages.json", output)
        finals = [r for r in json.loads(output.read_text())["results"] if r["event"] == "Stop"]
        self.assertTrue(finals[0]["text_caps_pass"])
        self.assertFalse(finals[1]["text_caps_pass"])
        self.provider.assert_not_called()

    def test_modified_source_is_rejected(self):
        path = self.transcript([message("Original", "1")])
        self.inventory()
        path.write_text(path.read_text().replace("Original", "Modified"))
        with self.assertRaisesRegex(ValueError, "source changed"):
            limits.replay(self.output / "inventory.json", self.output / "messages.json", self.root / "limits.json")

    def test_dry_run_seals_payload_without_call_or_output(self):
        output = self.root / "run.json"
        seal = runner.run(self.cases(), output, False, 1)
        self.assertEqual(seal["cases"], 1)
        self.assertEqual(set(seal["request_schemas_sha256"]), {"Stop", "UserPromptSubmit"})
        self.assertNotEqual(*seal["request_schemas_sha256"].values())
        self.assertFalse(output.exists())
        self.provider.assert_not_called()

    def test_exact_request_hash_is_recorded_before_send(self):
        output, cases = self.root / "run.json", self.cases()
        rows = json.loads(cases.read_text())
        rows[0]["view"].update(event="UserPromptSubmit", evidence_complete=True, goals=[], recent=[], active=None)
        cases.write_text(json.dumps(rows))
        def provider(body, key, timeout):
            before = json.loads(output.read_text())
            self.assertEqual(before["attempts"][0]["request_sha256"], runner.ns.digest(body))
            self.assertEqual(before["results"], [])
            return {"relation": "on_track", "confidence": .99, "aligned_probability": .99,
                    "navigation_probability": .01, "evidence": .99, "remind": .01,
                    "omission": .01, "contradiction": .01, "report_scope": "narrow", "scope_confidence": .99}, {}
        self.provider.side_effect = provider
        runner.run(cases, output, True, 1)
        result = json.loads(output.read_text())
        self.assertEqual(result["attempts"][0]["request_sha256"], result["results"][0]["request_sha256"])
        self.assertEqual(result["results"][0]["action"], "silent")
        self.provider.assert_called_once()

    def replay_fixture(self):
        cases = self.cases()
        rows = json.loads(cases.read_text())
        rows[0]["view"].update(event="UserPromptSubmit", evidence_complete=True, goals=[], recent=[], active=None)
        cases.write_text(json.dumps(rows))
        view = rows[0]["view"]
        judgment = {"relation": "on_track", "confidence": .99, "aligned_probability": .99,
                    "navigation_probability": .01, "evidence": .99, "remind": .01,
                    "omission": .01, "contradiction": .01, "report_scope": "narrow", "scope_confidence": .99}
        results = self.root / "results.json"
        results.write_text(json.dumps({"seal": {"cases_sha256": runner.ns.digest(cases.read_bytes()),
                                                "policy": runner.ns.DEFAULTS}, "results": [{
            "id": "one", "action": "abstain", "judgment": judgment,
            "view_sha256": runner.ns.digest(view),
            "request_sha256": runner.ns.digest(runner.ns.request_body(view, runner.ns.DEFAULTS["model"]))}]}))
        return cases, results

    def test_policy_replay_uses_exact_request_without_provider_call(self):
        cases, results = self.replay_fixture()
        with patch.object(policy_replay.ns, "ask", side_effect=AssertionError("No API during replay")):
            rows = policy_replay.replay(cases, results, self.root / "replay.json")
        self.assertEqual(rows[0]["final_action"], "silent")
        self.assertEqual(rows[0]["live_action"], "abstain")

    def test_policy_replay_refuses_judgments_from_a_different_question(self):
        cases, results = self.replay_fixture()
        report = json.loads(results.read_text())
        report["results"][0]["request_sha256"] = "0" * 64
        results.write_text(json.dumps(report))
        output = self.root / "replay.json"
        with self.assertRaisesRegex(ValueError, "Exact request changed"):
            policy_replay.replay(cases, results, output)
        self.assertFalse(output.exists())

    def test_changed_context_outside_target_is_rejected(self):
        path = self.transcript([message("Request", "1"),
                               message("Original", "2", "assistant", "commentary"),
                               message("Result", "3", "assistant", "final_answer")])
        self.inventory()
        path.write_text(path.read_text().replace("Original", "Modified"))
        with self.assertRaisesRegex(ValueError, "outside a target"):
            limits.replay(self.output / "inventory.json", self.output / "messages.json", self.root / "limits.json")

    def test_unknown_provider_outcome_is_recorded_and_not_retried(self):
        output, cases = self.root / "run.json", self.cases()
        self.provider.side_effect = TimeoutError("Possibly accepted")
        with self.assertRaises(SystemExit):
            runner.run(cases, output, True, 1)
        report = json.loads(output.read_text())
        self.assertEqual(len(report["attempts"]), 1)
        self.assertEqual(report["results"], [])
        self.assertEqual(report["failure"]["kind"], "TimeoutError")
        with self.assertRaisesRegex(ValueError, "not be repeated"):
            runner.run(cases, output, True, 1)
        self.provider.assert_called_once()

    def test_credential_payload_and_call_budget_rejected_before_send(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            runner.run(self.cases("fake-secret"), self.root / "run.json", True, 1)
        with self.assertRaisesRegex(ValueError, "budget"):
            runner.run(self.cases(), self.root / "run.json", True, 0)
        self.provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
