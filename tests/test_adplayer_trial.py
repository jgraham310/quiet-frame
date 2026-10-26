import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from adplayer_trial import make_plan, load_plan, launch_identity, trial_command, sha, TRIAL_ROOT
from build import write_trial_manifest


class Fixture:
    def __init__(self, root):
        self.root = Path(root)
        self.app = self.root / 'tv/app'
        self.backup = self.root / 'tv/backup'
        self.dbdir = self.root / 'tv/db'
        self.proc = self.root / 'tv/proc'
        self.users = self.root / 'tv/users'
        self.package = self.root / '.local/package-netcoreapp3.1-AdPlayer'
        for path in (self.app / 'bin/.native_image', self.app / 'res', self.backup / 'original',
                     self.backup / 'state', self.dbdir, self.proc, self.users / '1234', self.package / 'quiet-home'):
            path.mkdir(parents=True)
        self.old = {'AdPlayer.dll': b'original IL', 'AdPlayer.runtimeconfig.json': b'original config', 'AdPlayer.ni.dll': b'original cache'}
        for name, data in self.old.items():
            original = self.backup / 'original' / name
            original.write_bytes(data)
            live = self.app / 'bin' / ('.native_image/' + name if name.endswith('.ni.dll') else name)
            live.write_bytes(data)
            original.chmod(0o644 if name.endswith('.ni.dll') else 0o755)
            live.chmod(original.stat().st_mode & 0o777)
        (self.app / 'bin/other-library.dll').write_bytes(b'keep this library')
        self.database = self.dbdir / '.pkgmgr_parser.db'
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE package_app_info(app_id PRIMARY KEY,app_type,app_exec,app_disable,app_onboot,app_autorestart,app_preload,unrelated)')
            db.execute('INSERT INTO package_app_info VALUES(?,?,?,?,?,?,?,?)', ('com.samsung.tv.adplayer','dotnet-inhouse',str(self.app / 'bin/AdPlayer.dll'),'false','false','false','true','before'))
            db.execute('INSERT INTO package_app_info VALUES(?,?,?,?,?,?,?,?)', ('native-home','dotnet','home.dll','false','true','true','true','keep'))
            with sqlite3.connect(self.backup / 'state/.pkgmgr_parser.db') as saved:
                db.commit()
                db.backup(saved)
        (self.backup / 'state/original-files.sha256').write_text(''.join(sha(data) + '  ' + name + '\n' for name, data in self.old.items()))
        (self.backup / 'state/apps-before.csv').write_text('app_id,app_disable\ninstalled.app,false\nuninstalled.app,true\n')
        archive = self.backup / 'backup.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(self.backup / 'original', 'original')
            tar.add(self.backup / 'state', 'state')
        (self.backup / 'complete').write_text('complete\n')
        local = self.root / '.local/backups/backup-01'
        local.mkdir(parents=True)
        (local / 'backup.tar.gz').write_bytes(archive.read_bytes())
        stdout = ''
        for pid, path in ((10, '/usr/apps/com.samsung.tv.csfs/bin/csfs.dll'), (11, '/usr/apps/org.tizen.art-app/bin/ArtApp.dll')):
            self.process(pid, path)
            stdout += f'\nPID={pid}\nmatched_app_argument={path}\n{path}\nUid:\t1234\t1234\t1234\t1234\nGid:\t100\t100\t100\t100\n'
        self.record = {'model':'SYNTHETIC_FRAME','runtime':'3.1','uid':0,'euid':0,'staging_cleaned':True,'system_files_unchanged':True,
                       'commands':[{'exit_code':0,'timed_out':False,'stdout':stdout}], 'collected_files':{'adplayer-backup.tar.gz':{'sha256':sha(archive.read_bytes())}}}
        sessions = self.root / '.local/sessions'
        sessions.mkdir()
        (sessions / 'synthetic.json').write_text(json.dumps(self.record))
        for name in ('AdPlayer.dll', 'AdPlayer.runtimeconfig.json', 'AdPlayer.deps.json'):
            (self.package / name).write_bytes(json.dumps({'runtimeOptions':{'tfm':'netcoreapp3.1'}}).encode() if 'runtimeconfig' in name else b'new ' + name.encode())
        (self.package / 'quiet-home/tv.json').write_text('{"Family":"frame","Inputs":[],"EnablePrivateSettings":false}')
        (self.package / 'quiet-home/apps.json').write_text('[{"Id":"installed.app","Name":"Installed"},{"Id":"uninstalled.app","Name":"Absent"}]')
        (self.package / 'quiet-home/test.svg').write_bytes(b'synthetic artwork')
        helper = self.root / 'helper-build'
        helper.mkdir()
        for suffix in ('.dll', '.runtimeconfig.json', '.deps.json'):
            (helper / ('TrialLaunch' + suffix)).write_text('{"runtimeOptions":{"tfm":"netcoreapp3.1"}}' if 'runtimeconfig' in suffix else 'synthetic helper')
        write_trial_manifest(self.package, 'netcoreapp3.1', helper)
        self.directory, self.plan = make_plan(self.root, 'trial-01', 'backup-01', self.package, 'SYNTHETIC_FRAME', 'SYNTHETIC_FIRMWARE', '3.1')
        self.trial = self.root / 'tv/trials/trial-01'
        self.trial.mkdir(parents=True)
        with tarfile.open(self.directory / 'trial.tar.gz', 'r:gz') as tar:
            tar.extractall(self.trial, filter='data')
        env = {'D':str(self.trial),'A':str(self.app),'B':str(self.backup),'launch_uid':'1234','launch_gid':'100','backup_hash':sha(archive.read_bytes())}
        (self.trial / 'plan-env.sh').write_text('\n'.join(k + '=' + shlex.quote(v) for k,v in env.items()) + '\n')
        passwd = self.root / 'tv/passwd'
        passwd.write_text('synthetic:x:1234:100::/:/bin/sh\n')
        self.body = (ROOT / 'recipes/adplayer-trial.sh').read_text().replace('/opt/dbspace',str(self.dbdir)).replace('/proc/[0-9]*',str(self.proc) + '/[0-9]*').replace('/run/user',str(self.users)).replace('/etc/passwd',str(passwd))
        utilities = self.root / 'utilities'
        utilities.mkdir()
        sqlite = utilities / 'sqlite3'
        sqlite.write_text('#!' + sys.executable + '\n' + '''
import sqlite3,sys
args=[a for a in sys.argv[1:] if a not in ('-readonly','-bail')]
uri='file:'+args[0]+('?mode=ro' if '-readonly' in sys.argv else '?mode=rw')
with sqlite3.connect(uri,uri=True) as db:
    if len(args)>1:
        for row in db.execute(args[1]): print('|'.join(str(v) for v in row))
    else: db.executescript(sys.stdin.read())
''')
        sqlite.chmod(0o700)
        runuser = utilities / 'runuser'
        runuser.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> ' + shlex.quote(str(self.root / 'helper-calls')) + '\ntest "$2" = synthetic || exit 7\n')
        runuser.chmod(0o700)
        self.body = self.body.replace('/usr/sbin/runuser', str(runuser))
        self.environment = {**os.environ, 'PATH':str(utilities) + os.pathsep + os.environ['PATH']}
        self.prefix = '''id() { printf '0\\n'; }
chown() { :; }
chsmack() { :; }
stat() {
 if [ "$1" = -c ]; then
  case "$2" in
   %u:%g) printf '201:0\\n'; return;;
   %u:%g:%a) printf '201:0:'; command stat -c %a "$3"; return;;
   %u) printf '1234\\n'; return;;
  esac
 fi
 command stat "$@"
}
ls() { if [ "$1" = -dZ ]; then printf 'User::Pkg::com.samsung.tv.adplayer::RO %s\\n' "$2"; else command ls "$@"; fi; }
app_launcher() { printf '%s\\n' "$*" >> ''' + shlex.quote(str(self.root / 'stop-calls')) + '; rm -rf ' + shlex.quote(str(self.proc / '99')) + '; }\n'

    def process(self, pid, argument, uid=1234):
        directory = self.proc / str(pid)
        directory.mkdir()
        (directory / 'cmdline').write_bytes(b'/usr/bin/dotnet\0' + argument.encode() + b'\0')
        (directory / 'status').write_text(f'Uid:\t{uid}\t{uid}\t{uid}\t{uid}\nGid:\t100\t100\t100\t100\n')
        (directory / 'environ').write_bytes(b'UNRELATED_SECRET=do-not-copy\0DBUS_SESSION_BUS_ADDRESS=unix:path=/synthetic/bus\0')

    def run(self, action, fault=None):
        body = self.body
        if fault:
            needle, replacement = fault
            if needle not in body:
                raise AssertionError('Fault injection did not match')
            body = body.replace(needle, replacement, 1)
        path = self.trial / 'executed-test-script.sh'
        path.write_text(self.prefix + body)
        return subprocess.run(['sh', str(path), action], capture_output=True, text=True, env=self.environment)

    def ok(self, test, action, fault=None):
        result = self.run(action, fault)
        test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def preload(self):
        with sqlite3.connect(self.database) as db:
            return db.execute("SELECT app_preload FROM package_app_info WHERE app_id='com.samsung.tv.adplayer'").fetchone()[0]

    def original(self, test):
        for name, data in self.old.items():
            path = self.app / 'bin' / ('.native_image/' + name if name.endswith('.ni.dll') else name)
            test.assertEqual(path.read_bytes(), data)
            test.assertEqual(path.stat().st_mode & 0o777, 0o644 if name.endswith('.ni.dll') else 0o755)
        test.assertFalse((self.app / 'res/quiet-home').exists())
        test.assertFalse((self.app / 'bin/AdPlayer.deps.json').exists())
        test.assertEqual(self.preload(), 'true')


class TrialTests(unittest.TestCase):
    def test_pinned_prepare_extracts_only_to_trial_and_refuses_tampered_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = Fixture(temporary)
            (f.trial / 'trial.sh').write_text(f.prefix + f.body)
            files = {str(p.relative_to(f.trial)):p.read_bytes() for p in f.trial.rglob('*') if p.is_file() and p.name not in ('control.sha256','restore.sh')}
            controls = ''.join(sha(data) + '  ' + str(f.trial / name) + '\n' for name,data in sorted(files.items())).encode()
            files['control.sha256'] = controls
            (f.directory / 'control-pin.txt').write_text(sha(controls) + '\n')
            with tarfile.open(f.directory / 'trial.tar.gz', 'w:gz') as archive:
                for name,data in files.items():
                    member=tarfile.TarInfo(name)
                    member.size, member.mode = len(data), 0o600
                    archive.addfile(member,io.BytesIO(data))
            stage=f.root / 'staging' / ('archive-root-' + '0' * 16)
            stage.mkdir(parents=True)
            shutil.copyfile(f.directory / 'trial.tar.gz',stage / 'trial.tar.gz')
            shutil.rmtree(f.trial)
            command=trial_command(f.directory,'prepare','/home/owner/share/tmp/sdk_tools/' + stage.name)
            command=command.replace(str(TRIAL_ROOT),str(f.trial.parent)).replace('/home/owner/share/tmp/sdk_tools',str(stage.parent))
            result=subprocess.run(['sh'],input=command,text=True,capture_output=True,env=f.environment)
            self.assertEqual(result.returncode,0,result.stdout + result.stderr)
            f.original(self)
            (f.trial / 'trial.sh').write_text('exit 0\n')
            result=subprocess.run(['sh'],input=command,text=True,capture_output=True,env=f.environment)
            self.assertNotEqual(result.returncode,0)
            f.original(self)

    def test_plan_pins_evidence_build_and_inverse_and_filters_absent_apps(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = Fixture(temporary)
            before = (f.directory / 'trial.tar.gz').read_bytes()
            directory, plan = make_plan(f.root, 'trial-01', 'backup-01', f.package, 'SYNTHETIC_FRAME', 'SYNTHETIC_FIRMWARE', '3.1')
            self.assertEqual(plan['uid'], 1234)
            self.assertEqual(plan['catalog_app_count'], 1)
            self.assertEqual(before, (directory / 'trial.tar.gz').read_bytes())
            self.assertEqual(load_plan(f.root, 'trial-01', 'SYNTHETIC_FRAME', 'SYNTHETIC_FIRMWARE', '3.1')[1], plan)
            with tarfile.open(directory / 'trial.tar.gz', 'r:gz') as archive:
                catalog = json.loads(archive.extractfile('payload/res/quiet-home/apps.json').read())
                self.assertEqual([a['Id'] for a in catalog], ['installed.app'])
                inverse = archive.extractfile('restore.sh').read().decode()
                self.assertIn('sha256sum -c', inverse)
                self.assertNotIn('vconftool set', archive.extractfile('trial.sh').read().decode())
            for wrong_model, wrong_firmware, wrong_runtime in [('OTHER','SYNTHETIC_FIRMWARE','3.1'),('SYNTHETIC_FRAME','OTHER','3.1'),('SYNTHETIC_FRAME','SYNTHETIC_FIRMWARE','6.0')]:
                with self.assertRaises(ValueError):
                    load_plan(f.root, 'trial-01', wrong_model, wrong_firmware, wrong_runtime)
            (f.package / 'AdPlayer.dll').write_bytes(b'changed build')
            with self.assertRaises(ValueError):
                make_plan(f.root, 'other', 'backup-01', f.package, 'SYNTHETIC_FRAME', 'SYNTHETIC_FIRMWARE', '3.1')
            (f.root / '.local/backups/backup-01/backup.tar.gz').write_bytes(b'changed backup')
            with self.assertRaises(ValueError):
                load_plan(f.root, 'trial-01', 'SYNTHETIC_FRAME', 'SYNTHETIC_FIRMWARE', '3.1')

    def test_prepare_install_launch_and_restore_preserve_unrelated_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = Fixture(temporary)
            backup_bytes = {p:p.read_bytes() for p in f.backup.rglob('*') if p.is_file()}
            f.ok(self, 'prepare')
            f.original(self)
            f.ok(self, 'install')
            self.assertEqual(f.preload(), 'false')
            self.assertFalse((f.app / 'bin/.native_image/AdPlayer.ni.dll').exists())
            f.ok(self, 'launch')
            calls = (f.root / 'helper-calls').read_text()
            self.assertIn('launch 1234 100 home', calls)
            self.assertNotIn('UNRELATED_SECRET', calls)
            with sqlite3.connect(f.database) as db:
                db.execute("UPDATE package_app_info SET unrelated='concurrent' WHERE app_id='com.samsung.tv.adplayer'")
            f.process(99, str(f.app / 'bin/AdPlayer.dll'))
            f.ok(self, 'restore')
            f.original(self)
            self.assertIn('-u 1234 -k com.samsung.tv.adplayer', (f.root / 'stop-calls').read_text())
            f.ok(self, 'restore')
            with sqlite3.connect(f.database) as db:
                self.assertEqual(db.execute("SELECT unrelated FROM package_app_info WHERE app_id='com.samsung.tv.adplayer'").fetchone(), ('concurrent',))
                self.assertEqual(db.execute("SELECT app_onboot,app_preload,unrelated FROM package_app_info WHERE app_id='native-home'").fetchone(), ('true','true','keep'))
            self.assertEqual((f.app / 'bin/other-library.dll').read_bytes(), b'keep this library')
            self.assertEqual(backup_bytes, {p:p.read_bytes() for p in backup_bytes})

    def test_interrupted_installs_restore_from_each_mutation_phase(self):
        phases = ['    mv -T "$A/bin/.native_image/AdPlayer.ni.dll"',
                  '    mv -T "$D/resources-ready"',
                  '    for name in AdPlayer.runtimeconfig.json AdPlayer.deps.json AdPlayer.dll; do',
                  '        mv -T "$temp" "$A/bin/$name"',
                  '    printf \'installed\\n\' > "$D/installed"']
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                f = Fixture(temporary)
                f.ok(self, 'prepare')
                result = f.run('install', (phase, '    exit 87\n' + phase))
                self.assertEqual(result.returncode, 87, result.stdout + result.stderr)
                self.assertNotEqual(f.run('install').returncode, 0)
                f.ok(self, 'restore')
                f.original(self)

    def test_partial_temporary_copy_is_retained_and_rollback_can_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = Fixture(temporary)
            f.ok(self, 'prepare')
            needle = '        mv -T "$temp" "$A/bin/$name"'
            result = f.run('install', (needle, '        printf partial > "$temp"\n        exit 87\n' + needle))
            self.assertEqual(result.returncode, 87, result.stderr)
            needle = '        atomic_copy "$B/original/$name" "$A/$relative"\n'
            result = f.run('restore', (needle, needle + '        exit 88\n'))
            self.assertEqual(result.returncode, 88, result.stderr)
            f.ok(self, 'restore')
            f.original(self)
            self.assertEqual((f.trial / 'interrupted-AdPlayer.runtimeconfig.json.tmp').read_bytes(), b'partial')

    def test_changed_files_registry_cache_and_new_resource_paths_block_restore(self):
        for drift in ('entry','metadata','cache','registry','resource','resource-mode','symlink'):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as temporary:
                f = Fixture(temporary)
                f.ok(self, 'prepare')
                f.ok(self, 'install')
                if drift == 'entry': (f.app / 'bin/AdPlayer.dll').write_bytes(b'firmware update')
                if drift == 'metadata': (f.app / 'bin/AdPlayer.dll').chmod(0o755)
                if drift == 'cache': (f.app / 'bin/.native_image/AdPlayer.ni.dll').write_bytes(b'new native image')
                if drift == 'registry':
                    with sqlite3.connect(f.database) as db: db.execute("UPDATE package_app_info SET app_disable='true' WHERE app_id='com.samsung.tv.adplayer'")
                if drift == 'resource': (f.app / 'res/quiet-home/unexpected').write_bytes(b'do not delete')
                if drift == 'resource-mode': (f.app / 'res/quiet-home/test.svg').chmod(0o600)
                if drift == 'symlink': (f.app / 'res/quiet-home/test.svg').unlink(); (f.app / 'res/quiet-home/test.svg').symlink_to(f.app / 'bin/other-library.dll')
                before = {p:p.read_bytes() for p in f.app.rglob('*') if p.is_file()}
                self.assertNotEqual(f.run('restore').returncode, 0)
                self.assertEqual(before, {p:p.read_bytes() for p in before})
                self.assertEqual(f.preload(), 'false')

    def test_wrong_process_uid_and_original_metadata_stop_before_mutation(self):
        for drift in ('running','uid','mode'):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as temporary:
                f = Fixture(temporary)
                f.ok(self, 'prepare')
                if drift in ('running','uid'): f.process(99, str(f.app / 'bin/AdPlayer.dll'), uid=1234 if drift == 'running' else 4321)
                else: (f.app / 'bin/AdPlayer.dll').chmod(0o644)
                self.assertNotEqual(f.run('install').returncode, 0)
                self.assertFalse((f.trial / 'install-started').exists())
                self.assertEqual(f.preload(), 'true')

    def test_old_restore_cannot_overwrite_a_later_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = Fixture(temporary)
            f.ok(self, 'prepare')
            f.ok(self, 'install')
            f.ok(self, 'restore')
            (f.app / 'bin/AdPlayer.dll').write_bytes(b'newer trial')
            self.assertNotEqual(f.run('restore').returncode, 0)
            self.assertEqual((f.app / 'bin/AdPlayer.dll').read_bytes(), b'newer trial')

    def test_failed_resource_labeling_stops_before_any_installed_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = Fixture(temporary)
            f.ok(self, 'prepare')
            result = f.run('install', ('        chsmack -a "$label" "$path"', '        false'))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((f.trial / 'install-started').exists())
            f.original(self)

    def test_launch_identity_requires_two_consistent_non_root_native_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            f = Fixture(temporary)
            self.assertEqual(launch_identity([f.record]), (1234,100))
            broken = json.loads(json.dumps(f.record))
            broken['commands'][0]['stdout'] = broken['commands'][0]['stdout'].replace('Uid:\t1234\t1234\t1234\t1234','Uid:\t0\t0\t0\t0',1)
            with self.assertRaises(ValueError): launch_identity([broken])
            for action in ('prepare','install','launch','restore'):
                command = trial_command(f.directory, action, '/home/owner/share/tmp/sdk_tools/archive-root-' + '0' * 16)
                subprocess.run(['sh','-n'],input=command,text=True,check=True)
            with self.assertRaises(ValueError): trial_command(f.directory,'exec')


if __name__ == '__main__':
    unittest.main()
