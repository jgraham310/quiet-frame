"""Build an immutable, private AdPlayer trial and its inverse from device evidence."""
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import tarfile

from adplayer_backup import APP, ARCHIVE, backup_directory
from runtime_payloads import FRAMEWORKS

ROOT = Path(__file__).resolve().parents[1]
TRIAL_ROOT = PurePosixPath('/opt/usr/share/quiet-frame-trials')
ENTRY = ('AdPlayer.dll', 'AdPlayer.runtimeconfig.json', 'AdPlayer.deps.json')
ORIGINAL = ('AdPlayer.dll', 'AdPlayer.runtimeconfig.json', 'AdPlayer.ni.dll')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sessions(root, model):
    for path in sorted((Path(root) / '.local/sessions').glob('*.json'), reverse=True):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (isinstance(data, dict) and data.get('model') == model and data.get('uid') == 0
                and data.get('euid') == 0 and data.get('staging_cleaned') and data.get('system_files_unchanged')):
            yield data


def launch_identity(records):
    known = ('/usr/apps/com.samsung.tv.csfs/bin/csfs.dll', '/usr/apps/org.tizen.art-app/bin/ArtApp.dll')
    for record in records:
        for command in record.get('commands', []):
            if command.get('exit_code') != 0 or command.get('timed_out'):
                continue
            identities = {}
            for block in re.split(r'\nPID=\d+\n', command.get('stdout', ''))[1:]:
                uid = re.search(r'^Uid:\s+(\d+)\s+\1\s+\1\s+\1\s*$', block, re.M)
                gid = re.search(r'^Gid:\s+(\d+)\s+\1\s+\1\s+\1\s*$', block, re.M)
                for app in known:
                    if app in block.splitlines() or 'matched_app_argument=' + app in block.splitlines():
                        if uid and gid:
                            identities[app] = (int(uid[1]), int(gid[1]))
            if set(identities) == set(known) and len(set(identities.values())) == 1:
                uid, gid = next(iter(identities.values()))
                if uid > 0 and gid > 0:
                    return uid, gid
    raise ValueError('Require a clean launch-context record identifying both native Home and Art with the same UID/GID.')


def read_backup(path, records):
    raw = path.read_bytes()
    digest = sha(raw)
    if len(raw) > 4194304 or not any(
        record.get('collected_files', {}).get(ARCHIVE, {}).get('sha256') == digest
        for record in records
    ):
        raise ValueError('The local backup must match an archive returned by a clean session for this model.')
    members = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        total = 0
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] not in ('original', 'state'):
                raise ValueError('Unexpected recovery archive path.')
            if member.isdir():
                continue
            total += member.size
            if not member.isfile() or total > 33554432 or len(members) >= 64 or member.name in members:
                raise ValueError('Unsafe or oversized recovery archive.')
            members[member.name] = archive.extractfile(member).read()
    original_hashes = {}
    for line in members['state/original-files.sha256'].decode().splitlines():
        digest, name = line.split('  ', 1)
        if name not in ORIGINAL or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid originals manifest.')
        original_hashes[name] = digest
    if set(original_hashes) != set(ORIGINAL) or any(
        sha(members['original/' + name]) != digest for name, digest in original_hashes.items()
    ):
        raise ValueError('Recovery originals do not match their saved hashes.')
    rows = list(csv.DictReader(io.StringIO(members['state/apps-before.csv'].decode())))
    ids = {row['app_id'] for row in rows if row['app_disable'] == 'false'}
    return sha(raw), original_hashes, ids


def safe_relative(name):
    path = PurePosixPath(name)
    if (not re.fullmatch(r'[A-Za-z0-9_./-]{1,220}', name) or path.is_absolute()
            or '..' in path.parts or any(part.startswith('.') for part in path.parts)
            or str(path) != name):
        raise ValueError('Invalid trial file path: ' + name)
    return path


def package_files(package, framework):
    manifest = json.loads((package / 'trial-build.json').read_text())
    if manifest.get('version') != 1 or manifest.get('framework') != framework or manifest.get('assembly') != 'AdPlayer':
        raise ValueError('Rebuild the AdPlayer variant for the observed CLR before preparing a trial.')
    result = {}
    for name, digest in manifest['files'].items():
        relative = safe_relative(name)
        if name not in ENTRY and relative.parts[0] not in ('quiet-home', 'trial-helper'):
            raise ValueError('Unexpected file in the trial build manifest.')
        source = package / name
        if source.is_symlink() or not source.is_file() or sha(source.read_bytes()) != digest:
            raise ValueError('Trial package changed after its recorded build: ' + name)
        result[name] = source.read_bytes()
    required = {*ENTRY, 'quiet-home/tv.json', 'quiet-home/apps.json',
                *('trial-helper/TrialLaunch' + suffix for suffix in ('.dll', '.runtimeconfig.json', '.deps.json'))}
    if not required <= result.keys() or len(result) > 180 or sum(map(len, result.values())) > 16777216:
        raise ValueError('Incomplete or oversized trial build.')
    for prefix in ('AdPlayer', 'trial-helper/TrialLaunch'):
        if json.loads(result[prefix + '.runtimeconfig.json'])['runtimeOptions']['tfm'] != framework:
            raise ValueError('Trial runtime configuration mismatch.')
    config = json.loads(result['quiet-home/tv.json'])
    if (config.get('Family') != 'frame' or config.get('Inputs') != []
            or config.get('EnablePrivateSettings') or config.get('NativeHomeAppId') or config.get('ArtModeAppId')):
        raise ValueError('The first streaming-only trial requires empty Inputs, private settings off and unassigned native shortcuts.')
    return result


def make_plan(root, name, backup, package, model, firmware, runtime):
    backup_directory(name)
    backup_path = backup_directory(backup)
    framework = FRAMEWORKS[runtime]
    root = Path(root)
    records = list(sessions(root, model))
    uid, gid = launch_identity(records)
    backup_hash, originals, installed = read_backup(root / '.local/backups' / backup / 'backup.tar.gz', records)
    package = Path(package).resolve()
    if (root / '.local').resolve() not in package.parents:
        raise ValueError('Use the built package inside this checkout’s .local directory.')
    source = package_files(package, framework)
    catalog = json.loads(source['quiet-home/apps.json'])
    catalog = [app for app in catalog if app['Id'] in installed]
    if not catalog:
        raise ValueError('No packaged app IDs match enabled apps in the recovery snapshot.')
    source['quiet-home/apps.json'] = (json.dumps(catalog, indent=2) + '\n').encode()
    files = {}
    for path, data in source.items():
        target = ('helper/' + path.split('/', 1)[1] if path.startswith('trial-helper/') else
                  'payload/res/' + path if path.startswith('quiet-home/') else 'payload/bin/' + path)
        files[target] = data
    trial = TRIAL_ROOT / name
    plan = {'version': 1, 'name': name, 'backup': backup, 'model': model, 'firmware': firmware,
            'runtime': runtime, 'uid': uid, 'gid': gid, 'backup_sha256': backup_hash,
            'originals': originals, 'files': {path: sha(data) for path, data in sorted(files.items())},
            'catalog_app_count': len(catalog), 'routing_changes': []}
    env = {'D': str(trial), 'A': APP, 'B': str(backup_path), 'launch_uid': str(uid), 'launch_gid': str(gid),
           'backup_hash': backup_hash}
    files['plan-env.sh'] = ('\n'.join(key + '=' + shlex.quote(value) for key, value in env.items()) + '\n').encode()
    files['trial.sh'] = (ROOT / 'recipes/adplayer-trial.sh').read_bytes()
    original_paths = {'AdPlayer.ni.dll': 'bin/.native_image/AdPlayer.ni.dll', **{n: 'bin/' + n for n in ORIGINAL[:2]}}
    files['originals.tsv'] = ''.join(originals[n] + '\t' + n + '\t' + original_paths[n] + '\n' for n in ORIGINAL).encode()
    payload = {path.removeprefix('payload/'): sha(data) for path, data in files.items() if path.startswith('payload/')}
    files['payload.tsv'] = ''.join(digest + '\t' + path + '\n' for path, digest in sorted(payload.items())).encode()
    resource_paths = {'res/quiet-home'}
    for path in payload:
        if path.startswith('res/'):
            resource_paths.add(path)
            resource_paths.update(str(p) for p in PurePosixPath(path).parents if str(p).startswith('res/quiet-home'))
    files['resource-paths.txt'] = ('\n'.join(sorted(resource_paths)) + '\n').encode()
    plan_bytes = (json.dumps(plan, indent=2, sort_keys=True) + '\n').encode()
    files['plan.json'] = plan_bytes
    controls = ''.join(sha(data) + '  ' + str(trial / path) + '\n' for path, data in sorted(files.items()))
    files['control.sha256'] = controls.encode()
    pin = sha(files['control.sha256'])
    files['restore.sh'] = ("#!/bin/sh\nset -eu\nprintf '%s  %s\\n' " + shlex.quote(pin) + ' '
        + shlex.quote(str(trial / 'control.sha256')) + " | sha256sum -c -\nsha256sum -c "
        + shlex.quote(str(trial / 'control.sha256')) + '\nexec /bin/sh '
        + shlex.quote(str(trial / 'trial.sh')) + ' restore\n').encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for path, data in sorted(files.items()):
            member = tarfile.TarInfo(path)
            member.size, member.mode, member.mtime = len(data), 0o600, 0
            archive.addfile(member, io.BytesIO(data))
    archive_data = buffer.getvalue()
    if len(archive_data) > 4194304:
        raise ValueError('Trial archive exceeds the 4 MiB transfer limit.')
    directory = root / '.local/trials' / name
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    artifacts = {'trial.tar.gz': archive_data, 'plan.json': plan_bytes, 'control-pin.txt': (pin + '\n').encode(),
                 'restore.sh': files['restore.sh'], 'trial.sh': files['trial.sh']}
    # gzip timestamps differ on repeated generation. Reuse only byte-identical
    # planned controls, then verify every member of a retained archive.
    if (directory / 'trial.tar.gz').exists():
        if (directory / 'plan.json').read_bytes() != plan_bytes or (directory / 'control-pin.txt').read_text().strip() != pin:
            raise ValueError('Trial name already belongs to a different plan; use a new name.')
        with tarfile.open(directory / 'trial.tar.gz', 'r:gz') as saved:
            members = saved.getmembers()
            if len(members) != len(files) or any(not m.isfile() or m.name not in files or saved.extractfile(m).read() != files[m.name] for m in members):
                raise ValueError('Retained trial archive changed; it was not overwritten.')
        return directory, plan
    if any((directory / filename).exists() for filename in artifacts):
        raise ValueError('Incomplete local trial plan remains for inspection; use a new name.')
    for filename, data in artifacts.items():
        with (directory / filename).open('xb') as output:
            output.write(data)
        (directory / filename).chmod(0o600)
    return directory, plan


def load_plan(root, name, model, firmware, runtime):
    backup_directory(name)
    directory = Path(root) / '.local/trials' / name
    plan = json.loads((directory / 'plan.json').read_text())
    if (plan['name'], plan['model'], plan['firmware'], plan['runtime']) != (name, model, firmware, runtime):
        raise ValueError('Trial plan identity/runtime no longer matches this TV.')
    backup_hash, originals, _ = read_backup(Path(root) / '.local/backups' / plan['backup'] / 'backup.tar.gz', list(sessions(root, model)))
    if backup_hash != plan['backup_sha256'] or originals != plan['originals']:
        raise ValueError('Retain the verified local recovery copy before every trial operation.')
    pin = (directory / 'control-pin.txt').read_text().strip()
    if not re.fullmatch('[0-9a-f]{64}', pin):
        raise ValueError('Invalid private trial control pin.')
    archived = {}
    with tarfile.open(directory / 'trial.tar.gz', 'r:gz') as archive:
        total = 0
        for member in archive:
            safe_relative(member.name)
            total += member.size
            if not member.isfile() or member.name in archived or total > 16777216 or len(archived) > 200:
                raise ValueError('Invalid retained trial archive.')
            archived[member.name] = archive.extractfile(member).read()
    if sha(archived['control.sha256']) != pin or archived['plan.json'] != (directory / 'plan.json').read_bytes():
        raise ValueError('Retained trial controls changed.')
    control_paths = set()
    for line in archived['control.sha256'].decode().splitlines():
        digest, path = line.split('  ', 1)
        relative = str(PurePosixPath(path).relative_to(TRIAL_ROOT / name))
        if relative in control_paths or sha(archived[relative]) != digest:
            raise ValueError('Retained trial payload or inverse changed.')
        control_paths.add(relative)
    if set(archived) != control_paths | {'control.sha256', 'restore.sh'}:
        raise ValueError('Unexpected retained trial members.')
    return directory, plan


def trial_command(directory, action, staging=None):
    if action not in ('prepare', 'install', 'launch', 'restore'):
        raise ValueError('Unknown trial operation.')
    plan = json.loads((directory / 'plan.json').read_text())
    name = plan['name']
    backup_directory(name)
    trial = TRIAL_ROOT / name
    pin = (directory / 'control-pin.txt').read_text().strip()
    if not re.fullmatch('[0-9a-f]{64}', pin):
        raise ValueError('Invalid trial control pin.')
    q = shlex.quote
    command = 'set -eu\n'
    command += 'test ! -L ' + q(str(TRIAL_ROOT)) + '\ntest ! -L ' + q(str(trial)) + '\n'
    if action == 'prepare':
        stage = PurePosixPath(staging)
        if stage.parent != PurePosixPath('/home/owner/share/tmp/sdk_tools') or not re.fullmatch('archive-root-[0-9a-f]{16}', stage.name):
            raise ValueError('Trial preparation requires owned root-session staging.')
        archive = directory / 'trial.tar.gz'
        command += "printf '%s  %s\\n' " + q(sha(archive.read_bytes())) + ' ' + q(str(stage / 'trial.tar.gz')) + ' | sha256sum -c -\n'
        command += 'if [ ! -e ' + q(str(trial)) + ' ]; then\nmkdir -p ' + q(str(TRIAL_ROOT)) + '\nchmod 711 ' + q(str(TRIAL_ROOT)) + '\nmkdir ' + q(str(trial)) + '\nchmod 711 ' + q(str(trial)) + '\ntar -xzf ' + q(str(stage / 'trial.tar.gz')) + ' -C ' + q(str(trial)) + '\nfi\n'
    command += "printf '%s  %s\\n' " + q(pin) + ' ' + q(str(trial / 'control.sha256')) + ' | sha256sum -c -\n'
    command += 'sha256sum -c ' + q(str(trial / 'control.sha256')) + '\n/bin/sh ' + q(str(trial / 'trial.sh')) + ' ' + action + '\n'
    return command
