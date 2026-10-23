"""Keep host-built access payloads matched to the TV's observed CLR family."""
import hashlib
import json
from pathlib import Path

FRAMEWORKS = {"6.0": "net6.0", "3.1": "netcoreapp3.1"}
NAMES = ("SamsungTvArchiveRoot", "SamsungTvRootAgent")
FILES = tuple(name + suffix for name in NAMES for suffix in (".dll", ".runtimeconfig.json"))


def build_root(root, framework):
    if framework not in FRAMEWORKS.values():
        raise ValueError(f"Unsupported build framework: {framework}")
    base = Path(root) / ".local/build"
    return base if framework == "net6.0" else base / framework


def write_manifest(directory, framework):
    directory = Path(directory)
    for name in NAMES:
        actual = json.loads((directory / (name + ".runtimeconfig.json")).read_text())
        if actual.get("runtimeOptions", {}).get("tfm") != framework:
            raise ValueError("Built payload runtime configuration does not match the requested framework.")
    manifest = {"version": 1, "framework": framework,
                "files": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in FILES}}
    (directory / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def verified_payloads(root, runtime):
    if runtime not in FRAMEWORKS:
        raise ValueError(f"Unsupported observed runtime family: {runtime}")
    framework = FRAMEWORKS[runtime]
    directory = build_root(root, framework) / "payloads"
    hint = f"Build matching payloads first: python3 tools/build.py payloads --target-framework {framework}"
    try:
        manifest = json.loads((directory / "build-manifest.json").read_text())
        if (manifest.get("version") != 1 or manifest.get("framework") != framework
                or set(manifest.get("files", {})) != set(FILES)):
            raise ValueError("Payload build manifest has the wrong framework or file set.")
        for name in FILES:
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != manifest["files"][name]:
                raise ValueError("Payload files changed after their recorded build.")
        for name in NAMES:
            config = json.loads((directory / (name + ".runtimeconfig.json")).read_text())
            if config.get("runtimeOptions", {}).get("tfm") != framework:
                raise ValueError("Payload runtime configuration mismatch.")
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise ValueError(f"{error} {hint}") from error
    return directory
