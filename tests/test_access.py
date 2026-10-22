import base64
import gzip
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tv import check_identity, decode_pull, private_path, PROFILE, inventory_command
from device_profiles import load_profile


class AccessTests(unittest.TestCase):
    def test_target_identity_gate(self):
        legacy = load_profile(ROOT / "profiles/un75u8000ffxza-1300.9.json")
        check_identity(legacy["model"], legacy["firmware"], legacy, mutation=True)
        with self.assertRaises(ValueError):
            check_identity("ANOTHER_MODEL", legacy["firmware"], legacy)
        with self.assertRaises(ValueError):
            check_identity(legacy["model"], "ANOTHER_FIRMWARE", legacy)
        with self.assertRaises(ValueError):
            check_identity(legacy["model"], None, legacy)

    def test_default_frame_template_never_permits_root_or_mutation(self):
        self.assertEqual(PROFILE["family"], "frame")
        for mutation in (False, True):
            with self.assertRaisesRegex(ValueError, "inventory template"):
                check_identity(None, None, mutation=mutation)

    def test_frame_inventory_profile_does_not_authorize_deployment(self):
        profile = {**PROFILE, "model": "SYNTHETIC_FRAME", "firmware": "SYNTHETIC_FIRMWARE"}
        check_identity(profile["model"], profile["firmware"], profile)
        with self.assertRaisesRegex(ValueError, "inventory only"):
            check_identity(profile["model"], profile["firmware"], profile, mutation=True)
        with self.assertRaises(ValueError):
            check_identity("OTHER_FRAME", profile["firmware"], profile)
        with self.assertRaises(ValueError):
            check_identity(profile["model"], "OTHER_FIRMWARE", profile)

    def test_inventory_reads_registry_and_never_writes_preferences(self):
        command = inventory_command()
        self.assertIn("sqlite3 -readonly", command)
        self.assertNotIn("vconftool set", command)
        self.assertNotIn("app_launcher", command)
        self.assertNotIn("systemctl", command)

    def test_transfer_integrity(self):
        payload = b"synthetic contents only" * 100
        digest = hashlib.sha256(payload).hexdigest()
        body = base64.encodebytes(gzip.compress(payload)).decode()
        self.assertEqual(decode_pull(digest + "\n" + body), payload)
        with self.assertRaises(ValueError):
            decode_pull("0" * 64 + "\n" + body)
        with self.assertRaises(Exception):
            decode_pull(digest + "\n" + body[:-12])

    def test_private_outputs_cannot_escape_checkout_private_directory(self):
        with self.assertRaises(ValueError):
            private_path(ROOT / "public-backup.json")
        with self.assertRaises(ValueError):
            private_path(ROOT / ".local/../public-backup.json")

    def test_runtime_fallback_is_narrow(self):
        from samsung_tv_root.archive_root import _check_target, ArchiveRootError
        from unittest.mock import Mock
        client = Mock()
        capabilities = ("/usr/bin/dotnet cap_setgid,cap_sys_admin=ep\n"
                        "/usr/sbin/sdbd-tarlauncher cap_setgid,cap_setuid=ep")
        with patch("samsung_tv_root.archive_root._capture", side_effect=[
            capabilities, ArchiveRootError("Unknown option --list-runtimes"),
            "Microsoft.NETCore.App 6.0.9 [/usr/share/runtime/6.0.9]",
            "--to-command=COMMAND", "synthetic hash",
        ]) as capture:
            self.assertEqual(_check_target(client).runtime, "6.0")
            self.assertIn("System.Private.CoreLib.dll", capture.call_args_list[2].args[1])
        with patch("samsung_tv_root.archive_root._capture", side_effect=[
            capabilities, ArchiveRootError("permission denied"),
        ]):
            with self.assertRaises(ArchiveRootError):
                _check_target(client)


if __name__ == "__main__":
    unittest.main()
