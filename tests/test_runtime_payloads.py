import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
import asyncio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "vendor"))
from runtime_payloads import build_root, verified_payloads, verified_probe, write_manifest, NAMES
from samsung_tv_root.archive_root import probe, ArchiveRootError, _stage


class RuntimePayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def build_fixture(self, framework):
        directory = build_root(self.root, framework) / "payloads"
        directory.mkdir(parents=True)
        for name in NAMES:
            (directory / (name + ".dll")).write_bytes(b"synthetic payload " + framework.encode())
            (directory / (name + ".runtimeconfig.json")).write_text(json.dumps({"runtimeOptions": {"tfm": framework}}))
        write_manifest(directory, framework)
        return directory

    def test_observed_runtime_selects_its_own_build(self):
        modern = self.build_fixture("net6.0")
        with self.assertRaisesRegex(ValueError, "netcoreapp3.1"):
            verified_payloads(self.root, "3.1")
        older = self.build_fixture("netcoreapp3.1")
        self.assertEqual(verified_payloads(self.root, "3.1"), older)
        self.assertEqual(verified_payloads(self.root, "6.0"), modern)

    def test_unrecorded_or_changed_payloads_are_rejected(self):
        directory = self.build_fixture("net6.0")
        (directory / (NAMES[0] + ".dll")).write_bytes(b"stale or mismatched replacement")
        with self.assertRaisesRegex(ValueError, "changed after"):
            verified_payloads(self.root, "6.0")
        (directory / "build-manifest.json").unlink()
        with self.assertRaisesRegex(ValueError, "Build matching payloads"):
            verified_payloads(self.root, "6.0")

    def test_wrong_framework_or_incomplete_manifest_is_rejected(self):
        directory = self.build_fixture("net6.0")
        for manifest in ({"version": 1, "framework": "netcoreapp3.1", "files": {}},
                         {"version": 1, "framework": "net6.0", "files": {}}, None):
            (directory / "build-manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                verified_payloads(self.root, "6.0")

    def test_manifest_cannot_override_a_different_runtime_config(self):
        directory = self.build_fixture("net6.0")
        config = directory / (NAMES[0] + ".runtimeconfig.json")
        config.write_text('{"runtimeOptions":{"tfm":"netcoreapp3.1"}}')
        manifest = json.loads((directory / "build-manifest.json").read_text())
        manifest["files"][config.name] = hashlib.sha256(config.read_bytes()).hexdigest()
        (directory / "build-manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "configuration mismatch"):
            verified_payloads(self.root, "6.0")
        with self.assertRaisesRegex(ValueError, "does not match"):
            write_manifest(directory, "net6.0")

    def test_unknown_runtime_is_rejected(self):
        with self.assertRaises(ValueError):
            verified_payloads(self.root, "2.1")

    def probe_fixture(self):
        directory = build_root(self.root, "netcoreapp3.1") / "Probe"
        directory.mkdir(parents=True)
        (directory / "Probe.dll").write_bytes(b"synthetic compiled diagnostic")
        (directory / "Probe.runtimeconfig.json").write_text(
            '{"runtimeOptions":{"tfm":"netcoreapp3.1"}}')
        write_manifest(directory, "netcoreapp3.1", names=("Probe",))
        return directory

    def test_probe_requires_its_own_matching_recorded_build(self):
        with self.assertRaisesRegex(ValueError, "build.py probe"):
            verified_probe(self.root, "3.1")
        directory = self.probe_fixture()
        self.assertEqual(verified_probe(self.root, "3.1"), directory)
        with self.assertRaises(ValueError):
            verified_probe(self.root, "6.0")
        (directory / "Probe.dll").write_bytes(b"changed after compilation")
        with self.assertRaisesRegex(ValueError, "changed after"):
            verified_probe(self.root, "3.1")

    def test_diagnostic_probe_refuses_custom_commands_before_staging(self):
        with patch("samsung_tv_root.archive_root.SdbClient"), \
             patch("samsung_tv_root.archive_root.find_sdb", return_value="synthetic-sdb"), \
             patch("samsung_tv_root.archive_root._check_target", return_value=Mock(runtime="3.1")), \
             patch("samsung_tv_root.archive_root.RootAgentServer") as server:
            with self.assertRaisesRegex(ArchiveRootError, "no custom commands"):
                asyncio.run(probe("192.0.2.50", callback_host="192.0.2.51",
                                  diagnostic_probe=self.root, commands=("set-home",)))
            server.assert_not_called()

    def test_staged_probe_digests_are_checked_in_owned_session_directory(self):
        diagnostic = self.probe_fixture()
        payloads = self.build_fixture("netcoreapp3.1")
        client = Mock()
        def capture(client, command):
            if command.startswith("sha256sum "):
                name = command.rsplit("/", 1)[1]
                return hashlib.sha256((diagnostic / name).read_bytes()).hexdigest() + "  staged"
            return ""
        with patch("samsung_tv_root.archive_root._capture", side_effect=capture):
            _stage(client, self.root, payloads, "archive-root-synthetic", diagnostic)
        staged = [str(call.args[1]) for call in client.push.call_args_list]
        self.assertIn("/home/owner/share/tmp/sdk_tools/archive-root-synthetic/Probe.dll", staged)
        self.assertIn("/home/owner/share/tmp/sdk_tools/archive-root-synthetic/Probe.runtimeconfig.json", staged)
        with patch("samsung_tv_root.archive_root._capture", return_value="wrong-digest"):
            with self.assertRaisesRegex(ArchiveRootError, "digest mismatch"):
                _stage(client, self.root, payloads, "archive-root-synthetic", diagnostic)

    def test_changed_tv_runtime_stops_before_any_payload_is_staged(self):
        client = Mock()
        assessment = Mock(runtime="3.1")
        with patch("samsung_tv_root.archive_root.SdbClient", return_value=client), \
             patch("samsung_tv_root.archive_root.find_sdb", return_value="synthetic-sdb"), \
             patch("samsung_tv_root.archive_root._check_target", return_value=assessment), \
             patch("samsung_tv_root.archive_root._stage", new_callable=AsyncMock) as stage, \
             patch("samsung_tv_root.archive_root.RootAgentServer") as server:
            with self.assertRaisesRegex(ArchiveRootError, "runtime changed"):
                asyncio.run(probe("192.0.2.50", callback_host="192.0.2.51", expected_runtime="6.0"))
            stage.assert_not_called()
            server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
