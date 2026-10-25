import hashlib
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from adplayer_backup import APP, ARCHIVE, ORIGINALS, backup_command, backup_directory, observed_hashes


class AdPlayerBackupTests(unittest.TestCase):
    def test_names_staging_and_hash_inputs_are_bounded(self):
        expected = dict(zip(ORIGINALS, ("a" * 64, "b" * 64)))
        stage = "/home/owner/share/tmp/sdk_tools/archive-root-" + "0" * 16
        self.assertIn("base64 -d", backup_command("trial-01", stage, expected, "1234"))
        for name in ("../other", "a/b", "a;false", "", "a" * 65):
            with self.assertRaises(ValueError):
                backup_directory(name)
        with self.assertRaises(ValueError):
            backup_command("trial", "/tmp/not-owned", expected, "1234")
        with self.assertRaises(ValueError):
            backup_command("trial", stage, expected, "not-numeric")
        with self.assertRaises(ValueError):
            backup_command("trial", stage, {}, "1234")

    def test_hashes_require_matching_model_and_successful_clean_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / ".local/sessions"
            directory.mkdir(parents=True)
            stdout = "\n".join("a" * 64 + "  " + APP + "/bin/" + name for name in ORIGINALS)
            session = {"model": "SYNTHETIC", "uid": 0, "euid": 0,
                       "system_files_unchanged": True, "staging_cleaned": True,
                       "commands": [{"exit_code": 0, "timed_out": False, "stdout": stdout}]}
            path = directory / "session.json"
            path.write_text(json.dumps(session))
            self.assertEqual(set(observed_hashes(temporary, "SYNTHETIC")), set(ORIGINALS))
            with self.assertRaises(ValueError):
                observed_hashes(temporary, "OTHER")
            session["staging_cleaned"] = False
            path.write_text(json.dumps(session))
            with self.assertRaises(ValueError):
                observed_hashes(temporary, "SYNTHETIC")

    def test_backup_recipe_copies_snapshots_and_never_overwrites_originals(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            app, databases, backups, sdk = (base / name for name in ("app", "db", "backups", "sdk"))
            stage = sdk / ("archive-root-" + "0" * 16)
            (app / "bin/.native_image").mkdir(parents=True)
            (app / "res").mkdir()
            databases.mkdir()
            stage.mkdir(parents=True)
            (app / "bin/AdPlayer.dll").write_bytes(b"synthetic original IL")
            (app / "bin/AdPlayer.runtimeconfig.json").write_text('{"runtimeOptions":{"tfm":"netcoreapp2.0"}}')
            (app / "bin/.native_image/AdPlayer.ni.dll").write_bytes(b"synthetic native image")
            (app / "tizen-manifest.xml").write_text("<manifest/>")
            with sqlite3.connect(databases / ".pkgmgr_parser.db") as db:
                db.execute("CREATE TABLE package_app_info(app_id,app_type,app_exec,app_disable,app_onboot,app_autorestart,app_preload)")
                db.execute("INSERT INTO package_app_info VALUES (?,?,?,?,?,?,?)",
                           ("com.samsung.tv.adplayer", "dotnet-inhouse", str(app / "bin/AdPlayer.dll"),
                            "false", "false", "false", "true"))
            with sqlite3.connect(databases / ".app-context.db") as db:
                db.execute("CREATE TABLE key_filter(appid,key)")
                db.execute("INSERT INTO key_filter VALUES ('synthetic-home','XF86Home')")
            # Supply the sqlite3 CLI through Python's real SQLite backup API.
            utilities = base / "utilities"
            utilities.mkdir()
            stub = utilities / "sqlite3"
            stub.write_text("#!" + sys.executable + "\n" + """
import csv, shlex, sqlite3, sys
args=[arg for arg in sys.argv[1:] if arg not in ('-readonly','-header','-csv')]
source, query=args
with sqlite3.connect('file:'+source+'?mode=ro',uri=True) as db:
    if query.startswith('.backup '):
        with sqlite3.connect(shlex.split(query)[1]) as dest: db.backup(dest)
    else:
        cursor=db.execute(query)
        writer=csv.writer(sys.stdout,lineterminator='\\n')
        if '-header' in sys.argv: writer.writerow([col[0] for col in cursor.description])
        writer.writerows(cursor.fetchall())
""")
            stub.chmod(0o700)
            script = (ROOT / "recipes/backup-adplayer-originals.sh").read_text()
            for old, new in ((APP, app), ("/opt/dbspace", databases),
                             ("/opt/usr/share/quiet-frame-backups", backups),
                             ("/home/owner/share/tmp/sdk_tools", sdk),
                             ("/run/user", base / "users")):
                script = script.replace(old, str(new))
            prefix = """id() { printf '0\\n'; }
stat() {
    if [ "$1" = -c ] && [ "$2" = %u:%g ]; then printf '201:0\\n';
    else command stat "$@"; fi
}
vconftool() {
    if [ "$2" = db/appfw/home_appid ]; then printf 'synthetic-home\\n';
    else printf "Error: Get: Layer 'system' Key 'db/appfw/startup_appid': No such file or directory\\n"; return 1; fi
}
app_launcher() { printf '%s\\n' '--user=ID'; }
"""
            environment = {**os.environ, "PATH": str(utilities) + os.pathsep + os.environ["PATH"]}
            hashes = [hashlib.sha256((app / "bin" / name).read_bytes()).hexdigest() for name in ORIGINALS]
            before = {str(p): p.read_bytes() for root in (app, databases) for p in root.rglob("*") if p.is_file()}
            def run(name="trial-01", mode="create", expected=None):
                return subprocess.run(["sh", "-s", "--", name, str(stage), "1234",
                                       *(hashes if expected is None else expected), mode],
                                      input=prefix + script, text=True, capture_output=True, env=environment)
            result = run()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            target = backups / "trial-01"
            self.assertTrue((target / "complete").exists())
            self.assertEqual((target / "backup.tar.gz").read_bytes(), (stage / ARCHIVE).read_bytes())
            with tarfile.open(target / "backup.tar.gz", "r:gz") as archive:
                self.assertEqual(archive.extractfile("original/AdPlayer.dll").read(), (app / "bin/AdPlayer.dll").read_bytes())
                self.assertIn("state/.pkgmgr_parser.db", archive.getnames())
                self.assertIn("state/restore-plan.txt", archive.getnames())
            with sqlite3.connect(target / "state/.pkgmgr_parser.db") as snapshot:
                self.assertEqual(snapshot.execute("SELECT app_preload FROM package_app_info").fetchone(), ("true",))
            first_archive = (target / "backup.tar.gz").read_bytes()
            self.assertNotEqual(run().returncode, 0)
            self.assertEqual((target / "backup.tar.gz").read_bytes(), first_archive)
            self.assertEqual(run(mode="fetch").returncode, 0)
            bad = run(name="wrong-hash", expected=("0" * 64, hashes[1]))
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse((backups / "wrong-hash").exists())
            after = {str(p): p.read_bytes() for root in (app, databases) for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
