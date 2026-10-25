"""Prepare private AdPlayer recovery copies without installing anything."""
import base64
import json
from pathlib import Path, PurePosixPath
import re
import shlex

ROOT = Path(__file__).resolve().parents[1]
APP = "/opt/usr/apps/com.samsung.tv.adplayer"
ORIGINALS = ("AdPlayer.dll", "AdPlayer.runtimeconfig.json")
ARCHIVE = "adplayer-backup.tar.gz"


def backup_directory(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("Use a short backup name containing letters, digits, underscores or hyphens.")
    return PurePosixPath("/opt/usr/share/quiet-frame-backups") / name


def observed_hashes(root, model):
    for path in sorted((Path(root) / ".local/sessions").glob("*.json"), reverse=True):
        try:
            session = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(session, dict):
            continue
        if (session.get("model") != model or session.get("uid") != 0 or session.get("euid") != 0
                or not session.get("system_files_unchanged") or not session.get("staging_cleaned")):
            continue
        for result in session.get("commands", []):
            if result.get("exit_code") != 0 or result.get("timed_out"):
                continue
            matches = dict((name, digest) for digest, name in re.findall(
                r"^([0-9a-f]{64})[ \t]+" + re.escape(APP)
                + r"/bin/(AdPlayer\.dll|AdPlayer\.runtimeconfig\.json)[ \t]*$",
                result.get("stdout", ""), re.MULTILINE))
            if set(matches) == set(ORIGINALS):
                return matches
    raise ValueError("No verified AdPlayer hashes found locally. Run containers --adplayer-details first.")


def backup_command(name, staging, expected, sdk_uid, *, fetch_existing=False):
    backup_directory(name)
    staging = PurePosixPath(staging)
    if (staging.parent != PurePosixPath("/home/owner/share/tmp/sdk_tools")
            or not re.fullmatch(r"archive-root-[0-9a-f]{16}", staging.name)):
        raise ValueError("Backup transfer requires an owned temporary root session directory.")
    if not str(sdk_uid).isdigit():
        raise ValueError("Cannot record the SDK session's numeric UID.")
    if set(expected) != set(ORIGINALS) or any(
        not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in expected.values()
    ):
        raise ValueError("Require both hashes from the verified preflight.")
    encoded = base64.b64encode((ROOT / "recipes/backup-adplayer-originals.sh").read_bytes()).decode("ascii")
    args = (name, str(staging), str(sdk_uid), expected[ORIGINALS[0]], expected[ORIGINALS[1]],
            "fetch" if fetch_existing else "create")
    return "printf '%s' " + shlex.quote(encoded) + " | base64 -d | /bin/sh -s -- " + shlex.join(args)
