import base64
import gzip
import hashlib
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tv import (check_identity, decode_pull, private_path, PROFILE,
                inventory_command, home_preferences_command, platform_command, containers_command)
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
        for command in (inventory_command(), platform_command()):
            self.assertIn("sqlite3 -readonly", command)
            self.assertNotIn("vconftool set", command)
            self.assertNotIn("app_launcher", command)
            self.assertNotIn("systemctl", command)
            subprocess.run(["sh", "-n"], input=command, text=True, check=True)

    def run_preferences(self, startup, home="printf '%s\\n' 'home-value'"):
        stub = """set -eu
vconftool() {
    case "$2" in
        db/appfw/home_appid) %s ;;
        db/appfw/startup_appid) %s ;;
        *) return 99 ;;
    esac
}
""" % (home, startup)
        return subprocess.run(["sh"], input=stub + home_preferences_command(),
                              text=True, capture_output=True)

    def test_inventory_accepts_only_specific_absent_startup_diagnostic(self):
        diagnostic = "Error: Get: Layer 'system' Key 'db/appfw/startup_appid': No such file or directory"
        for stream in ("", " >&2"):
            result = self.run_preferences("printf '%s\\n' " + shlex.quote(diagnostic)
                                          + stream + "; return 1")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("home-value", result.stdout)
            self.assertIn("db/appfw/startup_appid: absent (not created)", result.stdout)

    def test_inventory_preserves_existing_startup_value(self):
        result = self.run_preferences("printf '%s\\n' 'startup-value'")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("startup-value", result.stdout)
        self.assertNotIn("absent", result.stdout)

    def test_inventory_does_not_hide_other_preference_errors(self):
        result = self.run_preferences("echo 'Permission denied' >&2; return 7")
        self.assertEqual(result.returncode, 7)
        self.assertIn("Permission denied", result.stderr)
        result = self.run_preferences("echo 'startup-value'", home="return 3")
        self.assertEqual(result.returncode, 3)

    def test_platform_queries_discover_managed_apps_without_upstream_containers(self):
        with sqlite3.connect(":memory:") as db:
            db.executescript("""
                CREATE TABLE package_app_info (
                    app_id TEXT, app_type TEXT, app_component TEXT, app_exec TEXT,
                    app_root_path TEXT, package TEXT, app_api_version TEXT,
                    app_disable TEXT, app_onboot TEXT, app_autorestart TEXT);
                CREATE TABLE key_filter (appid TEXT, key TEXT, longpress TEXT,
                    override TEXT, on_selector TEXT, request TEXT,
                    target_selector TEXT, args TEXT);
                INSERT INTO package_app_info VALUES
                    ('synthetic.managed', 'dotnet', 'uiapp', 'Managed.dll',
                     '/synthetic', 'synthetic', '6.0', 'false', 'false', 'false'),
                    ('org.tizen.art-app', 'capp', 'uiapp', '/synthetic/art',
                     '/synthetic', 'art', '6.0', 'false', 'false', 'false'),
                    ('synthetic.other', 'webapp', 'uiapp', 'index.html',
                     '/synthetic', 'other', '6.0', 'false', 'false', 'false');
                INSERT INTO key_filter VALUES ('synthetic.shell', 'XF86Home',
                    NULL, NULL, NULL, 'launch', 'synthetic.managed', NULL);
            """)
            changes = db.total_changes
            queries = [shlex.split(line)[-1] for line in platform_command().splitlines()
                       if line.startswith("sqlite3 ")]
            results = [db.execute(query).fetchall() for query in queries]
            self.assertEqual(len(results), 3)
            self.assertEqual({row[0] for row in results[1]},
                             {"synthetic.managed", "org.tizen.art-app"})
            self.assertEqual(results[2][0][1], "XF86Home")
            self.assertEqual(db.total_changes, changes)

    def test_container_inspection_reads_metadata_without_modifying_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            package = base / "writable/com.samsung.tv.adplayer"
            (package / "bin").mkdir(parents=True)
            (package / "info").mkdir()
            manifest = package / "info/tizen-manifest.xml"
            manifest.write_text('<manifest package="synthetic.readonly"/>')
            runtime = package / "bin/AdPlayer.runtimeconfig.json"
            runtime.write_text('{"runtimeOptions":{"tfm":"synthetic"}}')
            expected = {str(p): p.read_bytes() for p in package.rglob("*") if p.is_file()}
            command = containers_command().replace("/opt/usr/apps", str(base / "writable"))
            command = command.replace("/usr/apps", str(base / "system"))
            # No host registry is opened; actual filesystem readers inspect only
            # the private fixture and the remaining fixed directories are absent.
            prefix = "sqlite3() { printf '%s\\n' 'synthetic schema'; }\n"
            result = subprocess.run(["sh"], input=prefix + command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('synthetic.readonly', result.stdout)
            self.assertIn('runtimeOptions', result.stdout)
            self.assertIn('Directory absent', result.stdout)
            self.assertEqual(expected, {str(p): p.read_bytes() for p in package.rglob("*") if p.is_file()})
            detail = containers_command(True).replace("/opt/usr/apps", str(base / "writable"))
            result = subprocess.run(["sh"], input=prefix + detail, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(hashlib.sha256(runtime.read_bytes()).hexdigest(), result.stdout)
            self.assertIn('Entry assembly and runtime configuration', result.stdout)
            self.assertEqual(expected, {str(p): p.read_bytes() for p in package.rglob("*") if p.is_file()})

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
