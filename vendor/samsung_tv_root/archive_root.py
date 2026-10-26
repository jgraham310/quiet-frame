"""SDK archive launcher root route for owner-authorized TVs."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import ipaddress
import json
import re
import secrets
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from .resources import payload_directory
from .root_agent import RootAgentServer, generate_secret, write_secret
from .sdb import CaptureResult, SdbClient, SdbError, find_sdb, route_callback_host


STAGING_ROOT = PurePosixPath("/home/owner/share/tmp/sdk_tools")
ON_DEMAND = STAGING_ROOT / "on-demand"
PAYLOAD_FILES = (
    "SamsungTvArchiveRoot.dll",
    "SamsungTvRootAgent.dll",
)
RUNTIME_CONFIG_FILES = (
    "SamsungTvArchiveRoot.runtimeconfig.json",
    "SamsungTvRootAgent.runtimeconfig.json",
)
SYSTEM_HASH_COMMAND = "sha256sum /etc/passwd /usr/share/sdbd/public.pem"


class ArchiveRootError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetAssessment:
    capabilities: str
    original_hashes: str
    runtime: str


def _capture(client: SdbClient, command: str, timeout: float = 15.0) -> str:
    result = client.capture(command, timeout=timeout)
    if "[exit:0]" not in result.output:
        raise ArchiveRootError(
            f"SDK command failed: {command}: {result.output.strip()}"
        )
    return result.output.split("\n[exit:0]", 1)[0].strip()


def _file_capabilities(line: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for names, flags in re.findall(
        r"(cap_[a-z0-9_]+(?:,cap_[a-z0-9_]+)*)[=+]([eip]+)", line
    ):
        for name in names.split(","):
            result[name] = flags
    return result


def _check_target(client: SdbClient) -> TargetAssessment:
    client.connect()
    client.require_device()
    client.require_shell_injection()
    capabilities = _capture(client, "getcap /usr/bin/dotnet /usr/sbin/sdbd-tarlauncher")
    lines = capabilities.splitlines()
    dotnet = next((line for line in lines if "/usr/bin/dotnet" in line), "")
    launcher = next(
        (line for line in lines if "/usr/sbin/sdbd-tarlauncher" in line), ""
    )
    dotnet_caps = _file_capabilities(dotnet)
    launcher_caps = _file_capabilities(launcher)
    if not all(
        "e" in dotnet_caps.get(name, "") for name in ("cap_setgid", "cap_sys_admin")
    ):
        raise ArchiveRootError("dotnet lacks effective SETGID/SYS_ADMIN capabilities")
    if not all(
        "e" in launcher_caps.get(name, "") for name in ("cap_setgid", "cap_setuid")
    ):
        raise ArchiveRootError(
            "sdbd-tarlauncher lacks effective SETUID/SETGID capabilities"
        )
    try:
        runtimes = _capture(client, "/usr/bin/dotnet --list-runtimes")
    except ArchiveRootError as error:
        if "Unknown option --list-runtimes" not in str(error):
            raise
        # Samsung's custom host on this TV omits --list-runtimes.
        # Verify the actual CLR and core assembly at its resolved runtime path.
        runtimes = _capture(
            client,
            'd=$(readlink -f /usr/share/dotnet.tizen/netcoreapp) && '
            'test -f "$d/libcoreclr.so" && '
            'test -f "$d/System.Private.CoreLib.dll" && '
            'printf "Microsoft.NETCore.App %s [%s]\\n" "${d##*/}" "$d"',
        )
    majors = {
        int(match.group(1))
        for line in runtimes.splitlines()
        if (match := re.match(r"Microsoft\.NETCore\.App (\d+)\.\d+\.\d+\s+\[", line))
    }
    if any(major >= 6 for major in majors):
        runtime = "6.0"
    elif 3 in majors and any(
        re.match(r"Microsoft\.NETCore\.App 3\.1\.\d+\s+\[", line)
        for line in runtimes.splitlines()
    ):
        runtime = "3.1"
    else:
        raise ArchiveRootError("no supported Microsoft.NETCore.App runtime (3.1 or 6+)")
    tar_options = _capture(client, "/usr/bin/tar --help | grep -- --to-command")
    if "--to-command" not in tar_options:
        raise ArchiveRootError("TV tar does not support --to-command")
    return TargetAssessment(
        capabilities, _capture(client, SYSTEM_HASH_COMMAND), runtime
    )


def _openssl(*arguments: str) -> None:
    result = subprocess.run(
        ("openssl", *arguments), capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ArchiveRootError(
            f"openssl {arguments[0]} failed: {result.stderr.strip()}"
        )


def _prepare_artifacts(
    directory: Path,
    runtime: str,
    package: str,
    callback_host: str,
    callback_port: int,
    secret: bytes,
) -> None:
    staging = STAGING_ROOT / package
    private_key = directory / "private.pem"
    public_key = directory / "public.pem"
    archive = directory / f"{package}.tar.gz"
    signature = directory / f"{package}.tar.gz.signature"
    _openssl(
        "genpkey",
        "-algorithm",
        "RSA",
        "-pkeyopt",
        "rsa_keygen_bits:2048",
        "-out",
        str(private_key),
    )
    _openssl("pkey", "-in", str(private_key), "-pubout", "-out", str(public_key))
    (directory / "passwd").write_text(
        "owner:x:0:0:owner:/home/owner:/bin/sh\n", encoding="ascii"
    )
    runtime_version = "3.1.0" if runtime == "3.1" else "6.0.0"
    runtime_config = {
        "runtimeOptions": {
            "tfm": "netcoreapp3.1" if runtime == "3.1" else "net6.0",
            "rollForward": "Major" if runtime == "6.0" else "LatestPatch",
            "framework": {
                "name": "Microsoft.NETCore.App",
                "version": runtime_version,
            },
        }
    }
    for name in RUNTIME_CONFIG_FILES:
        (directory / name).write_text(
            json.dumps(runtime_config) + "\n", encoding="ascii"
        )
    write_secret(directory / "root-agent.token", secret)
    script = (
        "#!/bin/sh\n"
        f"exec /usr/bin/dotnet {staging}/SamsungTvRootAgent.dll "
        f"{callback_host} {callback_port} {staging}/root-agent.token {staging}\n"
    ).encode("ascii")
    with tarfile.open(archive, "w:gz") as output:
        member = tarfile.TarInfo("launch.sh")
        member.size = len(script)
        member.mode = 0o600
        member.mtime = 0
        output.addfile(member, io.BytesIO(script))
    _openssl(
        "dgst",
        "-sha256",
        "-sign",
        str(private_key),
        "-out",
        str(signature),
        str(archive),
    )
    _openssl(
        "dgst",
        "-sha256",
        "-verify",
        str(public_key),
        "-signature",
        str(signature),
        str(archive),
    )


def _stage(client: SdbClient, directory: Path, payloads: Path, package: str,
           diagnostic_probe: Path | None = None, session_files: tuple[Path, ...] = ()) -> None:
    staging = STAGING_ROOT / package
    _capture(client, f"/bin/mkdir -p {staging}")
    _capture(client, f"/bin/mkdir -p {ON_DEMAND}")
    for name in PAYLOAD_FILES:
        source = payloads / name
        if not source.is_file():
            raise ArchiveRootError(f"missing payload {source}; run make common-payload")
        client.push(source, staging / name)
    for name in RUNTIME_CONFIG_FILES:
        client.push(directory / name, staging / name)
    if diagnostic_probe is not None:
        for name in ("Probe.dll", "Probe.runtimeconfig.json"):
            source = diagnostic_probe / name
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            client.push(source, staging / name)
            actual = _capture(client, f"sha256sum {staging / name}").split()[0]
            if digest != actual:
                raise ArchiveRootError("Staged diagnostic probe digest mismatch.")
    for source in session_files:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        client.push(source, staging / source.name)
        if _capture(client, f"sha256sum {staging / source.name}").split()[0] != digest:
            raise ArchiveRootError("Staged session file digest mismatch.")
    for name in ("public.pem", "passwd", "root-agent.token"):
        client.push(directory / name, staging / name)
    archive_name = f"{package}.tar.gz"
    client.push(directory / archive_name, ON_DEMAND / archive_name)
    client.push(
        directory / f"{archive_name}.signature",
        ON_DEMAND / f"{archive_name}.signature",
    )


def _cleanup(client: SdbClient, package: str) -> bool:
    staging = STAGING_ROOT / package
    archive = ON_DEMAND / f"{package}.tar.gz"
    signature = ON_DEMAND / f"{package}.tar.gz.signature"
    _capture(client, f"/bin/rm -rf {staging}")
    _capture(client, f"/bin/rm -f {archive}")
    _capture(client, f"/bin/rm -f {signature}")
    for path in (staging, archive, signature):
        if _capture(client, f"test ! -e {path} && echo absent") != "absent":
            return False
    return True


async def probe(
    tv_host: str,
    *,
    model: str | None = None,
    callback_host: str | None = None,
    bind_host: str | None = None,
    sdb_timeout: float = 15.0,
    accept_timeout: float = 30.0,
    command_timeout: float = 45.0,
    commands: tuple[str, ...] = (),
    payloads: Path | None = None,
    expected_runtime: str | None = None,
    diagnostic_probe: Path | None = None,
    command_factory: Callable[[PurePosixPath], tuple[str, ...]] | None = None,
    collect_files: tuple[str, ...] = (),
    session_files: tuple[Path, ...] = (),
) -> dict[str, object]:
    ipaddress.IPv4Address(tv_host)
    callback = callback_host or route_callback_host(tv_host)
    ipaddress.IPv4Address(callback)
    bind = bind_host or callback
    ipaddress.IPv4Address(bind)
    client = SdbClient(find_sdb(), tv_host, timeout=sdb_timeout)
    assessment = await asyncio.to_thread(_check_target, client)
    if expected_runtime is not None and assessment.runtime != expected_runtime:
        raise ArchiveRootError("TV runtime changed since payload selection; stop and repeat preflight.")
    if command_factory is not None and (commands or diagnostic_probe is not None):
        raise ArchiveRootError("Session command factory cannot be combined with other command modes.")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", name) for name in collect_files):
        raise ArchiveRootError("Collect only simple filenames inside the owned session directory.")
    reserved = {*PAYLOAD_FILES, *RUNTIME_CONFIG_FILES, 'Probe.dll', 'Probe.runtimeconfig.json',
                'public.pem', 'passwd', 'root-agent.token', 'launcher.log'}
    session_files = tuple(Path(path) for path in session_files)
    if (len(session_files) > 4 or len({path.name for path in session_files}) != len(session_files)
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", path.name)
                   or path.name in reserved or not path.is_file() or path.is_symlink()
                   or path.stat().st_size > 4194304 for path in session_files)):
        raise ArchiveRootError("Stage only bounded, distinct session files with non-reserved simple filenames.")
    if diagnostic_probe is not None:
        if commands:
            raise ArchiveRootError("Diagnostic probe accepts no custom commands or arguments.")
        diagnostic_probe = Path(diagnostic_probe)
        for name in ("Probe.dll", "Probe.runtimeconfig.json"):
            if not (diagnostic_probe / name).is_file():
                raise ArchiveRootError(f"Missing diagnostic probe file: {name}")
    payloads = payloads or payload_directory(
        "common31" if assessment.runtime == "3.1" else "common"
    )
    for name in PAYLOAD_FILES:
        if not (payloads / name).is_file():
            raise ArchiveRootError(f"missing payload {payloads / name}")
    package = "archive-root-" + secrets.token_hex(8)
    if command_factory is not None:
        commands = command_factory(STAGING_ROOT / package)
    if diagnostic_probe is not None:
        # No arguments: the existing Probe's mutating set-home branch is never
        # selected. Stage and remove its files with the owned root session.
        commands = (f"/usr/bin/dotnet {STAGING_ROOT / package}/Probe.dll",)
    staging_started = False
    launch_task: asyncio.Task[CaptureResult] | None = None
    server = RootAgentServer(bind, 0, tv_host, generate_secret(), require_root=True)
    await server.start()
    try:
        with tempfile.TemporaryDirectory(prefix="samsung-tv-archive-root-") as temp:
            directory = Path(temp)
            _prepare_artifacts(
                directory,
                assessment.runtime,
                package,
                callback,
                server.listening_port,
                server.secret,
            )
            staging_started = True
            await asyncio.to_thread(_stage, client, directory, payloads, package, diagnostic_probe, session_files)
            command = (
                f"/usr/bin/dotnet {STAGING_ROOT / package}/SamsungTvArchiveRoot.dll "
                f"{package}"
            )
            launch_task = asyncio.create_task(
                asyncio.to_thread(
                    client.capture,
                    command,
                    callback_host=callback,
                    bind_host=bind,
                    timeout=accept_timeout + 20,
                )
            )
            try:
                connection = await server.accept(accept_timeout)
            except Exception as error:
                log_result = await asyncio.to_thread(
                    client.capture,
                    f"/bin/cat {STAGING_ROOT / package}/launcher.log",
                    timeout=10,
                )
                log = log_result.output.strip()
                launch_output = "pending"
                if launch_task.done():
                    try:
                        launch_output = launch_task.result().output.strip()
                    except Exception as launch_error:
                        launch_output = str(launch_error)
                raise ArchiveRootError(
                    f"no authenticated root callback; launch output: {launch_output}; "
                    f"launcher log: {log}"
                ) from error
            try:
                identity = await connection.ping()
                evidence = {
                    "model": model,
                    "host": tv_host,
                    "runtime": assessment.runtime,
                    "authenticated": True,
                    "uid": identity.uid,
                    "euid": identity.euid,
                    "gid": identity.gid,
                    "egid": identity.egid,
                    "cap_eff": identity.effective_capabilities,
                    "smack": identity.smack_label.strip(),
                    "preflight_capabilities": assessment.capabilities,
                }
                if commands:
                    evidence["commands"] = []
                    for command_text in commands:
                        result = await connection.execute(command_text, command_timeout)
                        evidence["commands"].append(
                            {
                                "command": command_text,
                                "exit_code": result.exit_code,
                                "timed_out": result.timed_out,
                                "stdout": result.stdout,
                                "stderr": result.stderr,
                            }
                        )
                if collect_files and commands and all(
                    item["exit_code"] == 0 and not item["timed_out"]
                    for item in evidence["commands"]
                ):
                    evidence["collected_files"] = {}
                    for name in collect_files:
                        artifact = await connection.read_file(STAGING_ROOT / package / name)
                        evidence["collected_files"][name] = {
                            "sha256": artifact.sha256,
                            "base64": base64.b64encode(artifact.data).decode("ascii"),
                        }
            finally:
                await connection.shutdown()
            if launch_task is not None:
                launch_result = await asyncio.wait_for(launch_task, timeout=15)
                if "[exit:0]" not in launch_result.output:
                    raise ArchiveRootError(
                        "launcher exited unsuccessfully: "
                        + launch_result.output.strip()
                    )
            return evidence
    finally:
        await server.close()
        if launch_task is not None and not launch_task.done():
            try:
                await asyncio.wait_for(launch_task, timeout=5)
            except Exception:
                pass
        cleaned = False
        if staging_started:
            try:
                cleaned = await asyncio.to_thread(_cleanup, client, package)
            except (ArchiveRootError, SdbError):
                pass
        final_hashes = await asyncio.to_thread(_capture, client, SYSTEM_HASH_COMMAND)
        if "evidence" in locals():
            evidence["system_files_unchanged"] = (
                final_hashes == assessment.original_hashes
            )
            evidence["staging_cleaned"] = cleaned
            if not evidence["system_files_unchanged"] or not cleaned:
                raise ArchiveRootError(
                    "root callback succeeded, but system-file or cleanup checks failed; "
                    f"staging={STAGING_ROOT / package}"
                )
