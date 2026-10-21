"""Offline migration of real legacy Windows state ACLs, without API requests."""
import base64
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "hooks/north-star/north_star.py"


def sddl(descriptor):
    from ctypes import wintypes
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    api.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
    output = ctypes.c_void_p()
    if not api.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, 1, 7, ctypes.byref(output), None):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.wstring_at(output)
    finally:
        kernel.LocalFree(output)


@unittest.skipUnless(os.name == "nt", "Windows protected DACL migration")
class AclTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("north_star_acl", SOURCE)
        self.ns = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ns)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "한글 user's home" / "north-star"
        self.sid = "legacy-thread-001"
        self.directory = self.root / "threads" / self.sid
        self.directory.mkdir(parents=True, mode=0o700)
        (self.directory / "sources").mkdir(mode=0o700)
        (self.directory / "history").mkdir(mode=0o700)
        self.state = self.ns.initial(self.sid)
        self.state.update(anchor_version=7, active="original", calls=[123],
                          nodes=[{"id": "original", "goal": "기존 목표", "refs": [{"hash": "original"}]}],
                          recovery={"observation_hash": "pending", "continuation_sent": True})
        (self.directory / "state.json").write_text(self.ns.dump(self.state), encoding="utf-8")
        (self.directory / "sources/original.jsonl").write_text("original human evidence\n", encoding="utf-8")
        (self.directory / "history/000006.json").write_text('{"previous":6}\n', encoding="utf-8")

    def test_store_repairs_legacy_tree_without_changing_evidence_or_state(self):
        originals = {p: p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        before = {p: self.ns.windows_descriptor(p)[0].raw for p in
                  (self.directory, self.directory / "sources", self.directory / "history")}
        self.assertTrue(all(self.ns.windows_descriptor(p)[1] for p in before))
        store = self.ns.Store(self.root, self.sid)
        self.assertEqual(store.read(), self.state)
        self.assertTrue(all(p.read_bytes() == value for p, value in originals.items()))
        backups = list((self.root / "acl-backups").glob("*.json"))
        self.assertEqual(len(backups), 3)
        for p, descriptor in before.items():
            after, protected = self.ns.windows_descriptor(p)
            self.assertFalse(protected)
            old_sddl, new_sddl = sddl(descriptor), sddl(after)
            self.assertEqual(old_sddl.split("D:")[0], new_sddl.split("D:")[0])
            explicit = lambda text: {ace for ace in re.findall(r"\([^()]+\)", text)
                                     if "ID" not in ace.split(";")[1]}
            self.assertEqual(explicit(old_sddl), explicit(new_sddl))
            record = next(json.loads(b.read_bytes()) for b in backups
                          if json.loads(b.read_bytes())["relative_path"] == p.relative_to(self.root).as_posix())
            self.assertEqual(base64.b64decode(record["security_descriptor_base64"]), descriptor)
        with patch.object(self.ns, "inherit_windows_acl", side_effect=AssertionError("not idempotent")):
            self.ns.Store(self.root, self.sid)
        self.assertEqual(list((self.root / "acl-backups").glob("*.json")), backups)

    def test_installer_sweeps_existing_threads_and_preserves_config(self):
        spec = importlib.util.spec_from_file_location("acl_installer", SOURCE.parents[2] / "scripts/install_north_star.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        config = self.root / "config.json"
        config.write_bytes(b'{"allow_export":false,"custom":42}\n')
        old_config = config.read_bytes()
        old_state = (self.directory / "state.json").read_bytes()
        receipt = installer.install(self.root.parent, preserve_config=True)
        self.assertEqual(receipt["state_acl_migration"]["repaired"], 3)
        self.assertEqual(config.read_bytes(), old_config)
        self.assertEqual((self.directory / "state.json").read_bytes(), old_state)
        self.assertEqual(installer.install(self.root.parent, preserve_config=True)["state_acl_migration"]["repaired"], 0)

    def test_junction_anywhere_below_parent_aborts_before_changing_acl(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        marker = outside / "state.json"
        marker.write_bytes(b"untouched")
        before = self.ns.windows_descriptor(marker)[0].raw
        link = self.directory / "sources/escape"
        result = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", "mklink", "/J",
                                 str(link), str(outside)], capture_output=True)
        if result.returncode and b"Access is denied" in result.stderr:
            self.skipTest("Sandbox denies junction creation; run this check outside the sandbox")
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.assertRaisesRegex(self.ns.Invalid, "reparse_state_path"):
            self.ns.repair_state_acls(self.root, self.sid)
        self.assertTrue(self.ns.windows_descriptor(self.directory)[1])
        self.assertEqual(self.ns.windows_descriptor(marker)[0].raw, before)
        self.assertEqual(marker.read_bytes(), b"untouched")

    def test_backup_failure_does_not_change_acl_or_original_state(self):
        before = (self.directory / "state.json").read_bytes()
        with patch.object(self.ns, "atomic", side_effect=PermissionError("backup denied")):
            with self.assertRaises(PermissionError):
                self.ns.Store(self.root, self.sid)
        self.assertTrue(self.ns.windows_descriptor(self.directory)[1])
        self.assertEqual((self.directory / "state.json").read_bytes(), before)

    def test_acl_failure_is_not_reported_as_a_success(self):
        with patch.object(self.ns, "inherit_windows_acl", side_effect=PermissionError("write DAC denied")):
            with self.assertRaises(PermissionError):
                self.ns.repair_state_acls(self.root, self.sid)
        self.assertTrue(self.ns.windows_descriptor(self.directory)[1])

    def test_parent_protection_is_repaired_before_legacy_children(self):
        # Protect a formerly inherited parent while preserving its explicit entries.
        result = subprocess.run(["icacls.exe", str(self.root / "threads"), "/inheritance:d"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.ns.windows_descriptor(self.root / "threads")[1])
        self.assertEqual(self.ns.repair_state_acls(self.root, self.sid)["repaired"], 4)
        self.assertFalse(self.ns.windows_descriptor(self.root / "threads")[1])
        self.assertEqual(self.ns.Store(self.root, self.sid).read(), self.state)

    def test_protected_source_file_is_repaired_without_changing_bytes(self):
        source = self.directory / "sources/original.jsonl"
        before = source.read_bytes()
        result = subprocess.run(["icacls.exe", str(source), "/inheritance:d"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.ns.windows_descriptor(source)[1])
        self.assertEqual(self.ns.repair_state_acls(self.root, self.sid)["repaired"], 4)
        self.assertFalse(self.ns.windows_descriptor(source)[1])
        self.assertEqual(source.read_bytes(), before)

    def test_non_windows_migration_does_not_touch_permissions(self):
        with patch.object(self.ns.os, "name", "posix"), patch.object(
                self.ns, "windows_descriptor", side_effect=AssertionError("Windows API on POSIX")):
            self.assertEqual(self.ns.repair_state_acls(self.root, self.sid), {"repaired": 0, "backups": []})


if __name__ == "__main__":
    unittest.main()
