"""Offline platform checks using real files and separate lock-owning processes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "hooks/north-star/north_star.py"
CHILD = """
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('north_star', sys.argv[1])
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)
store = ns.Store(Path(sys.argv[2]), 'platform-thread-001')
try:
    with store.lock():
        if sys.argv[3] == 'hold':
            print('locked', flush=True)
            sys.stdin.readline()
        else:
            state = store.read()
            state['revision'] += 1
            store.save(state)
            print('saved', flush=True)
except BlockingIOError:
    print('busy', flush=True)
"""


class PlatformTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("north_star_platform", SOURCE)
        self.ns = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ns)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "한글 user's home"
        self.store = self.ns.Store(self.root, "platform-thread-001")

    def child(self):
        result = subprocess.run([sys.executable, "-X", "utf8", "-c", CHILD,
                                 str(SOURCE), str(self.root), "save"],
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_other_process_cannot_write_until_lock_is_released(self):
        with self.store.lock():
            before = self.store.read()
            self.store.save(before)
            self.assertEqual(self.child(), "busy")
            self.assertEqual(self.store.read(), before)
        self.assertEqual(self.child(), "saved")
        self.assertEqual(self.store.read()["revision"], 1)

    @unittest.skipUnless(os.name == "nt", "Windows capability ACL inheritance")
    def test_new_thread_directories_preserve_inherited_sandbox_acl(self):
        import ctypes
        from ctypes import wintypes
        self.store.save(self.store.read())
        api = ctypes.windll.advapi32
        required = wintypes.DWORD()
        api.GetFileSecurityW(str(self.store.directory), 4, None, 0, ctypes.byref(required))
        descriptor = ctypes.create_string_buffer(required.value)
        self.assertTrue(api.GetFileSecurityW(str(self.store.directory), 4, descriptor,
                                             required.value, ctypes.byref(required)))
        control, revision = wintypes.WORD(), wintypes.DWORD()
        self.assertTrue(api.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)))
        self.assertFalse(control.value & 0x1000)  # SE_DACL_PROTECTED

    def test_lock_is_released_after_exception_and_process_exit(self):
        with self.assertRaisesRegex(RuntimeError, "intentional"):
            with self.store.lock():
                raise RuntimeError("intentional")
        self.assertEqual(self.child(), "saved")
        owner = subprocess.Popen([sys.executable, "-X", "utf8", "-c", CHILD,
                                  str(SOURCE), str(self.root), "hold"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            self.assertEqual(owner.stdout.readline().strip(), "locked")
            self.assertEqual(self.child(), "busy")
        finally:
            owner.kill()
            owner.communicate(timeout=15)
        self.assertEqual(self.child(), "saved")
        self.assertEqual(self.store.read()["revision"], 2)

    def test_utf8_state_and_audit_with_legacy_process_encoding(self):
        code = CHILD[:CHILD.index("try:")] + """
state = store.read()
state['nodes'] = json.load(sys.stdin)
with store.lock():
    store.save(state)
    store.audit('saved', label=state['nodes'][0]['goal'])
"""
        nodes = [{"goal": "한글 목표 😀"}]
        result = subprocess.run([sys.executable, "-X", "utf8=0", "-c", code,
                                 str(SOURCE), str(self.root)], input=json.dumps(nodes),
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.store.read()
        self.assertEqual(state["nodes"], nodes)
        raw = self.store.path.read_bytes()
        self.assertEqual(json.loads(raw.decode("utf-8")), state)
        self.assertEqual(self.store.read(), state)
        audit = self.store.directory / "audit.jsonl"
        self.assertEqual(json.loads(audit.read_bytes().decode("utf-8"))["label"], nodes[0]["goal"])

    @unittest.skipUnless(os.name == "nt", "Windows file sharing")
    def test_atomic_save_recovers_after_a_reader_releases_the_destination(self):
        self.store.save(self.store.read())
        before = self.store.path.read_bytes()
        reader = self.store.path.open("rb")
        replace = self.ns.os.replace
        denied = []

        def release_reader(source, destination):
            try:
                return replace(source, destination)
            except PermissionError as exc:
                self.assertEqual(Path(destination).read_bytes(), before)
                denied.append(exc.winerror)
                reader.close()
                raise

        state = self.store.read()
        state["revision"] = 1
        try:
            with patch.object(self.ns.os, "replace", side_effect=release_reader):
                self.store.save(state)
        finally:
            reader.close()
        self.assertTrue(denied)
        self.assertEqual(self.store.read(), state)
        self.assertFalse(list(self.store.directory.glob("*.tmp")))

    def test_atomic_save_preserves_old_state_if_replacement_remains_denied(self):
        self.store.save(self.store.read())
        before = self.store.path.read_bytes()
        denied = PermissionError("destination is busy")
        denied.winerror = 32
        with patch.object(self.ns.os, "replace", side_effect=denied), patch.object(self.ns.time, "sleep"):
            with self.assertRaises(PermissionError):
                self.store.save({**self.store.read(), "revision": 1})
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertFalse(list(self.store.directory.glob("*.tmp")))

    @unittest.skipUnless(os.name == "nt", "Windows generated hook command")
    def test_installed_hook_preserves_utf8_input_and_paths(self):
        spec = importlib.util.spec_from_file_location("install_north_star_platform",
                                                     REPO / "scripts/install_north_star.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        self.root.mkdir(parents=True, exist_ok=True)
        hooks = self.root / "hooks.json"
        existing = {"description": "기존 훅 😀", "hooks": {"Stop": [{"hooks": [{"command": "keep"}]}]}}
        hooks.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8-sig")
        receipt = installer.install(self.root)
        initial_hooks = hooks.read_bytes()
        installer.install(self.root)
        self.assertEqual(hooks.read_bytes(), initial_hooks)
        merged = json.loads(initial_hooks)
        self.assertEqual(merged["description"], existing["description"])
        self.assertEqual(merged["hooks"]["Stop"][0], existing["hooks"]["Stop"][0])
        config = json.loads((self.root / "north-star/config.json").read_bytes())
        self.assertFalse(config["allow_export"])
        sessions = self.root / "sessions"
        sessions.mkdir()
        transcript = sessions / "synthetic.jsonl"
        transcript.write_text(json.dumps({"type": "session_meta", "payload": {
            "id": "platform-thread-001", "source": "vscode"}}) + "\n", encoding="utf-8")
        for name in ("SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact", "PostCompact", "Stop"):
            event = {"hook_event_name": name, "session_id": "platform-thread-001",
                     "transcript_path": str(transcript), "prompt": "한글 요청 😀"}
            command = receipt["hooks"][name]["hooks"][0]["commandWindows"]
            with self.subTest(event=name):
                result = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command],
                                        input=json.dumps(event, ensure_ascii=False), text=True,
                                        capture_output=True, encoding="utf-8", timeout=15)
                self.assertEqual((result.returncode, result.stderr), (0, ""))
                if name in ("SessionStart", "UserPromptSubmit"):
                    self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"], name)
                else:
                    self.assertEqual(result.stdout, "")
        state_path = self.root / "north-star/threads/platform-thread-001/state.json"
        state = json.loads(state_path.read_bytes())
        self.assertTrue(state["bootstrap_sent"])
        self.assertEqual(state["checkpoint"]["event"], "PostCompact")
        # Echo the same arguments/stdin through the generated registration shell.
        script = self.root / "north-star/north_star.py"
        script.write_text("import json,sys\nprint(json.dumps({'args':sys.argv[1:], 'event':json.load(sys.stdin)}, ensure_ascii=False))\n",
                          encoding="utf-8")
        event = {"hook_event_name": "UserPromptSubmit", "prompt": "한글 요청 😀"}
        command = receipt["hooks"]["UserPromptSubmit"]["hooks"][0]["commandWindows"]
        result = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command],
                                input=json.dumps(event, ensure_ascii=False), text=True,
                                capture_output=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["event"], event)
        self.assertEqual(output["args"], ["--root", (self.root / "north-star").as_posix(), "hook"])
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
