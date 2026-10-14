"""Offline picker contracts. No test uses a live model or Codex account."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


picker = load("jev_skill_pick", ROOT / "hooks/jev-skill-pick/jev_skill_pick.py")
installer = load("register_skill_pick", ROOT / "scripts/register_jev_skill_pick.py")


def response(skills, choice="skill_1", confidence=0.96):
    ids = ["none", *(s["id"] for s in skills)]
    probabilities = {key: 0.0 for key in ids}
    probabilities[choice] = 1.0
    return {"model": "jev-test", "answers": {"skill": {"type": "choice", "choice": choice,
        "confidence": confidence, "probabilities": probabilities}}}


class PickerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.file = self.root / "SKILL.md"
        self.file.write_text("---\nname: frontend-design\ndescription: Build a frontend\n---\nInstructions")
        self.skills = [{"id": "skill_1", "name": "frontend-design", "description": "Build a frontend",
            "path": str(self.file)}]
        self.event = {"hook_event_name": "UserPromptSubmit", "prompt": "가격 섹션을 추가해줘", "cwd": str(self.root)}

    def test_actual_prompt_routes_and_returns_only_observed_skill(self):
        with patch.object(picker, "discover_skills", return_value=self.skills), patch.object(picker, "credential", return_value="fake-key"), patch.object(picker, "call_jev", return_value=response(self.skills)) as api:
            result = picker.evaluate(self.event, {"codex_command": "codex", "allow_prompt_export": True})
        self.assertEqual(result["status"], "selected")
        self.assertEqual(api.call_count, 1)
        payload = api.call_args.args[0]
        self.assertEqual(payload["state"]["user_request"], self.event["prompt"])
        self.assertIn("none", payload["questions"]["skill"]["criteria"])
        output = picker.hook_output(result)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "UserPromptSubmit")
        self.assertIn(str(self.file), output["additionalContext"])
        self.assertNotIn("fake-key", json.dumps(output))
        self.assertNotIn("decision", output)

    def test_none_and_low_confidence_add_no_context(self):
        for choice, confidence, status in [("none", 1, "no_match"), ("skill_1", 0.799, "uncertain")]:
            with self.subTest(status=status), patch.object(picker, "call_jev", return_value=response(self.skills, choice, confidence)):
                result = picker.pick("request", self.skills, "fake-key", "jev-latest", 0.8)
            self.assertEqual(result["status"], status)
            self.assertEqual(picker.hook_output(result), {})

    def test_unknown_ids_and_invalid_probabilities_are_rejected(self):
        mutations = [lambda a: a.update(choice="/tmp/arbitrary.py"), lambda a: a.update(confidence=True),
            lambda a: a.update(confidence=float("nan")), lambda a: a["probabilities"].update(extra=0),
            lambda a: a["probabilities"].update(skill_1=0.2), lambda a: a.update(type="noul")]
        for mutation in mutations:
            value = response(self.skills)
            mutation(value["answers"]["skill"])
            with self.assertRaises(ValueError):
                picker.validate_answer(value, self.skills)

    def test_commands_explicit_skills_and_other_events_never_call_api(self):
        cases = [{**self.event, "hook_event_name": "PostToolUse"}, {**self.event, "prompt": "/hooks"},
            {**self.event, "prompt": "$frontend-design 가격표 만들어줘"}, {**self.event, "prompt": ""},
            {**self.event, "cwd": "."}]
        with patch.object(picker, "call_jev") as api, patch.object(picker, "discover_skills") as catalog:
            for event in cases:
                self.assertEqual(picker.hook_output(picker.evaluate(event, {})), {})
        api.assert_not_called()
        catalog.assert_not_called()

    def test_missing_key_and_invalid_threshold_do_not_request_catalog(self):
        with patch.object(picker, "credential", return_value=None), patch.object(picker, "discover_skills") as catalog:
            self.assertEqual(picker.evaluate(self.event, {"allow_prompt_export": True})["status"], "missing_api_key")
            self.assertEqual(picker.evaluate(self.event, {"min_confidence": float("nan")})["status"], "invalid_config")
        catalog.assert_not_called()

    def test_export_requires_explicit_opt_in(self):
        with patch.object(picker, "credential") as key, patch.object(picker, "discover_skills") as catalog:
            self.assertEqual(picker.evaluate(self.event, {})["status"], "export_not_enabled")
        key.assert_not_called()
        catalog.assert_not_called()

    def test_configured_key_is_never_sent_when_it_occurs_in_prompt_or_catalog(self):
        config = {"allow_prompt_export": True, "codex_command": "codex"}
        with patch.object(picker, "credential", return_value="fake-key"), patch.object(picker, "discover_skills", return_value=self.skills) as catalog, patch.object(picker, "call_jev") as api:
            result = picker.evaluate({**self.event, "prompt": "use fake-key"}, config)
            self.assertEqual(result["status"], "credential_in_prompt")
            catalog.assert_not_called()
            catalog.return_value = [{**self.skills[0], "description": "contains fake-key"}]
            self.assertEqual(picker.evaluate(self.event, config)["status"], "credential_in_catalog")
        api.assert_not_called()

    def test_env_credentials_are_literal_and_process_key_wins(self):
        (self.root / ".env").write_text("OTHER_KEY=ignored\nexport TYPESAFE_API_KEY='literal-$(command)'\n")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(picker.credential(self.root, None), "literal-$(command)")
        with patch.dict(os.environ, {"JEV_API_KEY": "process-key"}, clear=True):
            self.assertEqual(picker.credential(self.root, None), "process-key")

    def test_disabled_missing_duplicate_and_explicit_only_skills_are_excluded(self):
        row = {**self.skills[0], "enabled": True}
        self.assertEqual(len(picker.normalize_skills([row, row, {**row, "enabled": False}, {**row, "path": "/missing/SKILL.md"}])), 1)
        (self.root / "agents").mkdir()
        (self.root / "agents/openai.yaml").write_text("policy:\n  allow_implicit_invocation: false\n")
        self.assertEqual(picker.normalize_skills([row]), [])

    def test_native_catalog_includes_only_enabled_installed_plugins(self):
        responses = [{}, {"data": [{"skills": [{**self.skills[0], "enabled": True}], "errors": []}]},
            {"marketplaces": [{"name": "personal", "path": "/tmp/marketplace.json", "plugins": [
                {"name": "disabled", "enabled": False, "installed": True},
                {"name": "plugin", "enabled": True, "installed": True},
            ]}], "marketplaceLoadErrors": []}]
        client = Mock()
        client.request.side_effect = responses
        client.request_many.return_value = [{"plugin": {"skills": [{**self.skills[0], "enabled": True}]}}]
        with patch.object(picker, "CodexCatalog", return_value=client):
            skills = picker.discover_skills(self.root, "codex")
        self.assertEqual(len(skills), 1)  # same physical skill is not offered twice
        self.assertEqual(client.request_many.call_args.args, ([("plugin/read", {"pluginName": "plugin", "marketplacePath": "/tmp/marketplace.json"})],))
        client.close.assert_called_once()

    def test_large_catalog_preserves_every_candidate_and_rechecks_finalists(self):
        skills = [{**self.skills[0], "id": f"skill_{i}", "name": f"skill-{i}"} for i in range(1, 256)]
        groups = picker.batches("request", skills, "jev-latest")
        self.assertEqual([len(g) for g in groups], [254, 1])
        self.assertEqual([s for group in groups for s in group], skills)
        with patch.object(picker, "call_jev", side_effect=[response(groups[0]), response(groups[1], "skill_255"), response([skills[0], skills[-1]], "skill_255")]) as api:
            result = picker.pick("request", skills, "fake-key", "jev-latest", 0.8)
        self.assertEqual(result["skill"]["id"], "skill_255")
        self.assertEqual(api.call_count, 3)

    def test_remote_plugin_uses_backend_id_and_exact_materialized_version(self):
        with tempfile.TemporaryDirectory() as home:
            skill_path = Path(home) / "plugins/cache/remote/plugin/2.0/skills/frontend-design/SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("skill")
            client = Mock()
            client.request.side_effect = [{}, {"data": [{"skills": [], "errors": []}]},
                {"marketplaces": [{"name": "remote", "path": None, "plugins": [
                    {"name": "plugin", "version": "2.0", "remotePluginId": "backend-plugin-id", "enabled": True, "installed": True}]}], "marketplaceLoadErrors": []}]
            client.request_many.return_value = [{"plugin": {"skills": [{"name": "frontend-design", "description": "Build a frontend", "path": None, "enabled": True}]}}]
            with patch.dict(os.environ, {"CODEX_HOME": home}), patch.object(picker, "CodexCatalog", return_value=client):
                rows = picker.discover_skills(self.root, "codex")
            self.assertEqual(rows[0]["path"], str(skill_path.resolve()))
            self.assertEqual(rows[0]["name"], "plugin:frontend-design")
            self.assertEqual(client.request_many.call_args.args[0][0][1]["pluginName"], "backend-plugin-id")

    def test_hook_entrypoint_fails_open_without_logging_provider_secrets(self):
        config = self.root / "picker.json"
        config.write_text("not valid JSON")
        result = subprocess.run([sys.executable, str(ROOT / "hooks/jev-skill-pick/jev_skill_pick.py"), "--config", str(config)], input=json.dumps(self.event), capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_provider_failure_never_leaks_error_or_blocks_prompt(self):
        with patch.object(picker, "evaluate", side_effect=OSError("fake-key and private prompt")), patch.object(sys, "argv", ["picker"]), patch.object(sys, "stdin", Mock(buffer=io.BytesIO(json.dumps(self.event).encode()))), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(picker.main(), 0)
        self.assertEqual(output.getvalue(), "")


class RegistrationTests(unittest.TestCase):
    def test_registration_preserves_other_hooks_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = {"description": "Existing hooks", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "existing"}]}]}}
            (root / "hooks.json").write_text(json.dumps(old))
            installer.register(root)
            first = (root / "hooks.json").read_bytes()
            installer.register(root)
            self.assertEqual((root / "hooks.json").read_bytes(), first)
            updated = json.loads(first)
            self.assertEqual(updated["hooks"]["Stop"], old["hooks"]["Stop"])
            self.assertEqual(len(updated["hooks"]["UserPromptSubmit"]), 1)
            self.assertEqual(len(list(root.glob("hooks.json.before-*"))), 1)

    def test_conflicting_installation_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "hooks").mkdir()
            installed = root / "hooks/jev-skill-pick.py"
            installed.write_text("user changes")
            with self.assertRaises(ValueError):
                installer.register(root)
            self.assertEqual(installed.read_text(), "user changes")
            self.assertFalse((root / "hooks.json").exists())


if __name__ == "__main__":
    unittest.main()
