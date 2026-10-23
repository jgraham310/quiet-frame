#!/usr/bin/env python3
"""Build locally; never redistribute Samsung reference assemblies."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
from runtime_payloads import FRAMEWORKS, build_root, write_manifest

ROOT = Path(__file__).resolve().parents[1]


def package_launcher(build_dir, source_assets, destination):
    """Package assets with local overrides, without leaking the local filenames."""
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(build_dir / "Home/BixbyPromotion.dll", destination / "BixbyPromotion.dll")
    shutil.copyfile(build_dir / "QuickLaunch/QuickLaunch.dll", destination / "QuickLaunch.dll")
    shutil.copyfile(build_dir / "Probe/Probe.dll", destination / "Probe.dll")
    assets = destination / "quiet-home"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(source_assets, assets)
    local_catalog = source_assets / "apps.local.json"
    if local_catalog.exists():
        shutil.copyfile(local_catalog, assets / "apps.json")
    (assets / "apps.local.json").unlink(missing_ok=True)
    local_tv = source_assets / "tv.local.json"
    if local_tv.exists():
        shutil.copyfile(local_tv, assets / "tv.json")
    (assets / "tv.local.json").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["payloads", "launcher", "all"])
    parser.add_argument("--dotnet", default=os.environ.get("DOTNET", "dotnet"))
    parser.add_argument("--framework", type=Path, default=ROOT / ".local/tv-framework")
    parser.add_argument("--target-framework", choices=tuple(FRAMEWORKS.values()), default="net6.0",
                        help="CLR target from doctor output, not from the Tizen version number")
    args = parser.parse_args()
    output_root = build_root(ROOT, args.target_framework)
    jobs = []
    if args.target in ("payloads", "all"):
        # A failed rebuild must not leave a manifest blessing partially replaced binaries.
        (output_root / "payloads/build-manifest.json").unlink(missing_ok=True)
        for name in ("SamsungTvArchiveRoot", "SamsungTvRootAgent"):
            jobs.append((ROOT / f"vendor/payload-source/{name}.csproj", "payloads", name, []))
    if args.target in ("launcher", "all"):
        for name in ("Tizen.NUI", "Tizen.Applications.Common", "Tizen.System", "Tizen"):
            if not (args.framework / f"{name}.dll").is_file():
                parser.error(f"Missing {name}.dll. Read docs/04-launcher.md; these are not bundled.")
        for name in ("Home", "QuickLaunch"):
            jobs.append((ROOT / f"launcher/src/{name}.csproj", name, name,
                         [f"-p:TV_FRAMEWORK_DIR={args.framework.resolve()}"]))
        jobs.append((ROOT / "launcher/probe/Probe.csproj", "Probe", "Probe", []))
    for project, output, intermediate, extra in jobs:
        subprocess.run([
            args.dotnet, "build", str(project), "-c", "Release", "--nologo",
            "-o", str(output_root / output),
            f"-p:BaseIntermediateOutputPath={ROOT / '.local/obj' / args.target_framework / intermediate}/",
            f"-p:TargetFramework={args.target_framework}",
            "-p:Deterministic=true",
            f"-p:PathMap={ROOT}=/_/quiet-tizen", *extra,
        ], check=True, env={**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"})
    if args.target in ("payloads", "all"):
        write_manifest(output_root / "payloads", args.target_framework)
    if args.target in ("launcher", "all"):
        destination = ROOT / ".local/package"
        if args.target_framework != "net6.0":
            destination = ROOT / (".local/package-" + args.target_framework)
        package_launcher(output_root, ROOT / "launcher/assets", destination)
        print(f"Deployable files: {destination.relative_to(ROOT)}. Review the catalog and input mapping before use.")


if __name__ == "__main__":
    main()
