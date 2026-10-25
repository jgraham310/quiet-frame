#!/usr/bin/env python3
"""Explicit-target, profile-gated Samsung TV access. Start with docs/10-frame.md."""
import argparse
import asyncio
import base64
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import sys
from datetime import datetime, timezone
from device_profiles import DEFAULT_PROFILE, load_profile, check_identity as profile_identity
from runtime_payloads import FRAMEWORKS, verified_payloads, verified_probe

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
from samsung_tv_root.archive_root import probe, _check_target, _capture
from samsung_tv_root.sdb import SdbClient, find_sdb

PROFILE = load_profile()
STAGE = "/home/owner/share/tmp/sdk_tools/quiet-tizen"


def private_path(path):
    path = Path(path).expanduser().resolve()
    private = (ROOT / ".local").resolve()
    if path == private or private not in path.parents:
        raise ValueError("Private files must be inside this checkout's .local/ directory.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def save_private(path, data):
    path = private_path(path)
    path.write_bytes(data)
    path.chmod(0o600)


def observed_model(client):
    client.connect()
    client.require_device()
    rows = [line.split() for line in client.run(("devices",), check=True).stdout.splitlines()]
    rows = [row for row in rows if row and row[0] == client.serial]
    if len(rows) != 1 or len(rows[0]) < 3:
        raise ValueError("Cannot identify the explicitly selected device from SDB.")
    return rows[0][-1]


def check_identity(model, firmware, profile=None, *, mutation=False):
    profile_identity(model, firmware, PROFILE if profile is None else profile, mutation=mutation)


def home_preferences_command():
    # A missing startup key is an observation, never permission to create it.
    # Only accept vconftool's specific missing-key diagnostic; other errors fail.
    return """read_optional_vconf() {
    if output=$(vconftool get "$1" 2>&1); then
        printf '%s\\n' "$output"
    else
        status=$?
        case "$output" in
            *"Key '$1': No such file or directory"*)
                printf '%s: absent (not created)\\n' "$1" ;;
            *) printf '%s\\n' "$output" >&2; return "$status" ;;
        esac
    fi
}
vconftool get db/appfw/home_appid
read_optional_vconf db/appfw/startup_appid
"""


def inventory_command():
    # No source switching, preference writes, unit stops or package modifications.
    # Missing private schemas remain explicit failures, not compatibility evidence.
    return """set -eu
uname -srmo
readlink -f /usr/share/dotnet.tizen/netcoreapp
sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db '.schema package_app_info'
sqlite3 -readonly -header -csv /opt/dbspace/.pkgmgr_parser.db 'SELECT app_id,app_disable,app_onboot,app_autorestart FROM package_app_info ORDER BY app_id;'
sqlite3 -readonly /opt/dbspace/.app-context.db '.schema key_filter'
""" + home_preferences_command()


def platform_command():
    # Fixed read-only queries: discover candidates, never select a replacement
    # container or launch an Art Mode app based on its name alone.
    return """set -eu
printf '\\n=== Application types ===\\n'
sqlite3 -readonly -header -csv /opt/dbspace/.pkgmgr_parser.db 'SELECT app_type,COUNT(*) AS count FROM package_app_info GROUP BY app_type ORDER BY app_type;'
printf '\\n=== Managed and launcher-related application metadata ===\\n'
sqlite3 -readonly -header -csv /opt/dbspace/.pkgmgr_parser.db "SELECT app_id,app_type,app_component,app_exec,app_root_path,package,app_api_version,app_disable,app_onboot,app_autorestart FROM package_app_info WHERE lower(app_type) LIKE '%dotnet%' OR lower(app_exec) LIKE '%.dll%' OR lower(app_id) LIKE '%promotion%' OR lower(app_id) LIKE '%quicklaunch%' OR app_id IN ('com.samsung.tv.bixby-promotion','com.samsung.tv.bixby-prov','com.samsung.tv.coba.home','com.samsung.tv.coba.art','org.tizen.art-app','org.tizen.tv-viewer','org.tizen.menu','org.tizen.app-selector') ORDER BY app_id;"
printf '\\n=== Home and Art application key filters ===\\n'
sqlite3 -readonly -header -csv /opt/dbspace/.app-context.db "SELECT appid,key,longpress,override,on_selector,request,target_selector,args FROM key_filter WHERE lower(key) LIKE '%home%' OR appid IN ('com.samsung.tv.coba.home','org.tizen.tv-viewer','org.tizen.art-app') ORDER BY appid,key;"
printf '\\n=== Home preferences ===\\n'
""" + home_preferences_command() + """
printf '\\n=== Framework assembly paths ===\\n'
find -L /usr/share/dotnet.tizen -maxdepth 6 -type f \\( -name Tizen.NUI.dll -o -name Tizen.Applications.Common.dll -o -name Tizen.System.dll -o -name Tizen.dll \\) -print
printf '\\n=== Native API library paths ===\\n'
for library in /usr/lib/libcapi-appfw-app-operation-tv.so* /usr/lib/libsource-api.so* /usr/lib/libcapi-media-sound-manager-tv.so*; do
    if [ -e "$library" ]; then
        readlink -f "$library"
    fi
done
"""


def pull_command(remote):
    if not remote.startswith("/") or "\0" in remote or "\n" in remote:
        raise ValueError("Use an absolute, single-line TV file path.")
    # The upstream command channel captures at most 1 MiB per stream.
    # A compressed transfer is bounded before emitting any base64.
    return f"""set -eu
test -f {shlex.quote(remote)}
test "$(stat -c %s {shlex.quote(remote)})" -le 33554432
t=$(mktemp /run/quiet-tizen-pull.XXXXXX)
trap 'rm -f "$t"' EXIT HUP INT TERM
gzip -c {shlex.quote(remote)} > "$t"
test "$(wc -c < "$t")" -le 760000 || {{ echo 'File too large; split a snapshot into smaller files first.' >&2; exit 1; }}
sha256sum {shlex.quote(remote)} | cut -d ' ' -f 1
base64 "$t"
"""


def containers_command():
    # Inspect vendor package metadata only. Names here are comparison samples,
    # not approved replacement containers or cleanup targets.
    return """set -eu
printf '\\n=== Package registry tables ===\\n'
sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'package%' ORDER BY name;"
printf '\\n=== Package metadata schema ===\\n'
sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db '.schema package_info'
printf '\\n=== Application-control metadata schema ===\\n'
sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db "SELECT name,sql FROM sqlite_master WHERE type='table' AND (name LIKE '%appcontrol%' OR name LIKE '%privilege%' OR name LIKE '%permission%') ORDER BY name;"
printf '\\n=== Existing managed package layouts ===\\n'
for root in /opt/usr/apps/com.samsung.tv.adplayer /opt/usr/apps/com.samsung.tv.ContentsBrowser /opt/usr/apps/com.samsung.tv.quickpanel /usr/apps/com.samsung.tv.csfs /usr/apps/org.tizen.art-app; do
    printf '\\nPackage directory: %s\\n' "$root"
    if [ ! -d "$root" ]; then
        printf 'Directory absent\\n'
        continue
    fi
    stat -c 'owner=%u group=%g mode=%a path=%n' "$root" "$root/bin"
    if labels=$(ls -ldZ "$root" "$root/bin" 2>&1); then
        printf '%s\\n' "$labels"
    else
        printf 'Security-label listing unavailable: %s\\n' "$labels"
    fi
    find "$root" -maxdepth 2 -type f \\( -name '*.runtimeconfig.json' -o -name '*manifest*.xml' \\) -print -exec head -c 12000 {} \\;
    printf '\\n'
done
printf '\\n=== Package and launch tool paths ===\\n'
for tool in app_launcher pkgcmd pkgmgr-cli aul-launch vconftool chsmack; do
    if command -v "$tool"; then :; else printf '%s: unavailable\\n' "$tool"; fi
done
"""


def decode_pull(stdout):
    digest, encoded = stdout.split("\n", 1)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Missing transfer digest.")
    compressed = base64.b64decode("".join(encoded.split()), validate=True)
    data = gzip.decompress(compressed)
    if len(data) > 33554432 or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Transfer size or digest mismatch; file was not saved.")
    return data


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="The owner's TV IPv4 address; never auto-discovered")
    parser.add_argument("--firmware", help="Operator-verified version from the TV's About screen")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE,
                        help="Exact device profile; default is the non-deployable Frame template")
    parser.add_argument("--sdb", help="Path to Samsung's separately installed SDB")
    parser.add_argument("--callback-host", help="This computer's LAN IPv4 if route detection is wrong")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("identify", help="Read only the explicitly selected SDB device identity")
    sub.add_parser("doctor", help="Read SDB identity and archive-route capabilities; does not obtain root")
    sub.add_parser("inventory", help="Collect read-only runtime/registry information using temporary root")
    sub.add_parser("platform", help="Read application entry points, Home routing and framework paths")
    sub.add_parser("containers", help="Read package schemas, owners/labels, manifests and runtime configurations")
    sub.add_parser("sources", help="Run fixed read-only Probe queries for source IDs and native Home handler")
    sub.add_parser("root-check", help="Temporarily obtain root and run id; no configuration changes")
    run = sub.add_parser("exec", help="Execute one reviewed command or short script using temporary root")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--command")
    source.add_argument("--script", type=Path)
    run.add_argument("--arg", action="append", default=[], help="Positional argument passed to --script")
    pull = sub.add_parser("pull", help="Read and verify one bounded file into ignored .local/")
    pull.add_argument("remote")
    pull.add_argument("local", type=Path)
    push = sub.add_parser("push", help="Upload one file to the SDK staging directory, not to system paths")
    push.add_argument("local", type=Path)
    push.add_argument("name", help="Simple staging filename")
    args = parser.parse_args()
    profile = load_profile(args.profile)
    ipaddress.IPv4Address(args.host)
    if args.callback_host:
        ipaddress.IPv4Address(args.callback_host)
    if args.sdb:
        os.environ["SDB"] = str(Path(args.sdb).expanduser().resolve())
    client = SdbClient(find_sdb(), args.host, timeout=15)
    model = observed_model(client)
    print("SDB model:", model)
    if args.action == "identify":
        print("Read firmware from Settings > Support > About This TV; SDB identity is not compatibility proof.")
        return
    if args.action == "doctor":
        assessment = _check_target(client)
        print("Archive-route runtime family:", assessment.runtime)
        print("Required build framework:", FRAMEWORKS[assessment.runtime])
        print(assessment.capabilities)
        print(_capture(client, "uname -srmo; readlink -f /usr/share/dotnet.tizen/netcoreapp"))
        print("Preflight only. Firmware must be read on the TV; root is not yet confirmed.")
        return
    check_identity(model, args.firmware, profile, mutation=args.action in ("exec", "push"))
    if args.action == "push":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", args.name):
            raise ValueError("Use a simple staging filename without directory components.")
        if not args.local.is_file():
            raise ValueError("Upload source must be a file.")
        _capture(client, f"mkdir -p {STAGE}")
        remote = PurePosixPath(STAGE) / args.name
        client.push(args.local.resolve(), remote)
        digest = hashlib.sha256(args.local.read_bytes()).hexdigest()
        actual = _capture(client, f"sha256sum {shlex.quote(str(remote))}").split()[0]
        if digest != actual:
            raise ValueError("Uploaded file digest mismatch.")
        print(f"Verified staging file: {remote}. Remove it after deployment.")
        return
    if args.action == "root-check":
        command = "id"
    elif args.action == "inventory":
        command = inventory_command()
    elif args.action == "platform":
        command = platform_command()
    elif args.action == "containers":
        command = containers_command()
    elif args.action == "sources":
        command = None
    elif args.action == "pull":
        private_path(args.local)
        command = pull_command(args.remote)
    elif args.script:
        script = args.script.read_bytes()
        if len(script) > 45000:
            raise ValueError("Script too large for the bounded command channel; split into phases.")
        encoded = base64.b64encode(script).decode()
        command = f"printf '%s' {shlex.quote(encoded)} | /bin/sh -s -- " + shlex.join(args.arg)
    else:
        if args.arg:
            raise ValueError("--arg requires --script.")
        command = args.command
    assessment = _check_target(client)
    payloads = verified_payloads(ROOT, assessment.runtime)
    diagnostic_probe = verified_probe(ROOT, assessment.runtime) if args.action == "sources" else None
    result = asyncio.run(probe(
        args.host, model=model, callback_host=args.callback_host,
        payloads=payloads, expected_runtime=assessment.runtime,
        commands=() if diagnostic_probe is not None else (command,), command_timeout=30,
        diagnostic_probe=diagnostic_probe,
    ))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    log = ROOT / ".local/sessions" / f"{stamp}.json"
    save_private(log, (json.dumps(result, indent=2) + "\n").encode())
    if result.get("uid") != 0 or result.get("euid") != 0:
        raise ValueError("The callback did not prove UID/EUID 0.")
    if not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
        raise ValueError("Root session cleanup checks failed; inspect the private session log.")
    response = result["commands"][0]
    if response["stderr"]:
        print(response["stderr"], file=sys.stderr, end="")
    if args.action in ("sources", "containers"):
        print(response["stdout"], end="")
    if response["exit_code"] or response["timed_out"]:
        raise RuntimeError(f"Command failed ({response['exit_code']}, timeout={response['timed_out']}). "
                           f"Private log: {log.relative_to(ROOT)}")
    if args.action == "pull":
        save_private(args.local, decode_pull(response["stdout"]))
        print("Verified file saved inside .local/.")
    elif args.action == "inventory":
        print(f"Private inventory saved in {log.relative_to(ROOT)}. Review locally; do not publish raw output.")
    elif args.action not in ("sources", "containers"):
        print(response["stdout"], end="")
    print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as error:
        print(f"Stopped: {error}", file=sys.stderr)
        sys.exit(1)
