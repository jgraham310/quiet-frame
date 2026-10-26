#!/usr/bin/env python3
"""Build locally; never redistribute Samsung reference assemblies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from runtime_payloads import FRAMEWORKS, build_root, write_manifest

ROOT = Path(__file__).resolve().parents[1]


def package_launcher(build_dir, source_assets, destination, home_assembly="BixbyPromotion"):
    """Package assets with local overrides, without leaking the local filenames."""
    destination.mkdir(parents=True, exist_ok=True)
    home_folder = "Home" if home_assembly == "BixbyPromotion" else "Home-" + home_assembly
    for suffix in (".dll", ".runtimeconfig.json", ".deps.json"):
        source = build_dir / home_folder / (home_assembly + suffix)
        if suffix == ".dll" or home_assembly != "BixbyPromotion" or source.is_file():
            shutil.copyfile(source, destination / source.name)
    if home_assembly == "BixbyPromotion":
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


def write_trial_manifest(destination, framework, helper):
    helper_dir = destination / "trial-helper"
    helper_dir.mkdir(exist_ok=True)
    for suffix in (".dll", ".runtimeconfig.json", ".deps.json"):
        shutil.copyfile(helper / ("TrialLaunch" + suffix), helper_dir / ("TrialLaunch" + suffix))
    files = [destination / ("AdPlayer" + suffix) for suffix in (".dll", ".runtimeconfig.json", ".deps.json")]
    files += sorted((destination / "quiet-home").rglob("*")) + sorted(helper_dir.iterdir())
    for path in files:
        if path.is_symlink():
            raise ValueError("Trial packages cannot contain symlinks.")
    manifest = {"version": 1, "framework": framework, "assembly": "AdPlayer",
                "files": {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in files if p.is_file()}}
    (destination / "trial-build.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["payloads", "probe", "trial-helper", "launcher", "all"])
    parser.add_argument("--dotnet", default=os.environ.get("DOTNET", "dotnet"))
    parser.add_argument("--framework", type=Path, default=ROOT / ".local/tv-framework")
    parser.add_argument("--target-framework", choices=tuple(FRAMEWORKS.values()), default="net6.0",
                        help="CLR target from doctor output, not from the Tizen version number")
    parser.add_argument("--home-assembly", choices=("BixbyPromotion", "AdPlayer"), default="BixbyPromotion",
                        help="Entry assembly for an explicitly inspected container; does not install it")
    args = parser.parse_args()
    output_root = build_root(ROOT, args.target_framework)
    trial_build = args.target in ("launcher", "all") and args.home_assembly == "AdPlayer"
    trial_destination = ROOT / (".local/package" + ("-" + args.target_framework if args.target_framework != "net6.0" else "") + "-AdPlayer")
    if trial_build:
        (trial_destination / "trial-build.json").unlink(missing_ok=True)
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
        for name in (("Home", "QuickLaunch") if args.home_assembly == "BixbyPromotion" else ("Home",)):
            output = name if name != "Home" or args.home_assembly == "BixbyPromotion" else "Home-" + args.home_assembly
            extra = [f"-p:TV_FRAMEWORK_DIR={args.framework.resolve()}"]
            if name == "Home":
                extra.append(f"-p:TV_HOME_ASSEMBLY={args.home_assembly}")
            jobs.append((ROOT / f"launcher/src/{name}.csproj", output, output, extra))
    if args.target in ("probe", "launcher", "all"):
        (output_root / "Probe/build-manifest.json").unlink(missing_ok=True)
        jobs.append((ROOT / "launcher/probe/Probe.csproj", "Probe", "Probe", []))
    if args.target == "trial-helper" or trial_build:
        jobs.append((ROOT / "launcher/trial/TrialLaunch.csproj", "TrialLaunch", "TrialLaunch", []))
    for project, output, intermediate, extra in jobs:
        subprocess.run([
            args.dotnet, "build", str(project), "-c", "Release", "--nologo",
            "-o", str(output_root / output),
            f"-p:BaseIntermediateOutputPath={ROOT / '.local/obj' / args.target_framework / intermediate}/",
            f"-p:TV_TARGET_FRAMEWORK={args.target_framework}",
            "-p:Deterministic=true",
            f"-p:PathMap={ROOT}=/_/quiet-tizen", *extra,
        ], check=True, env={**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"})
    if args.target in ("payloads", "all"):
        write_manifest(output_root / "payloads", args.target_framework)
    if args.target in ("probe", "launcher", "all"):
        write_manifest(output_root / "Probe", args.target_framework, names=("Probe",))
    if args.target in ("launcher", "all"):
        destination = ROOT / ".local/package"
        if args.target_framework != "net6.0":
            destination = ROOT / (".local/package-" + args.target_framework)
        if args.home_assembly != "BixbyPromotion":
            destination = destination.with_name(destination.name + "-" + args.home_assembly)
        package_launcher(output_root, ROOT / "launcher/assets", destination, args.home_assembly)
        if trial_build:
            write_trial_manifest(destination, args.target_framework, output_root / "TrialLaunch")
        print(f"Deployable files: {destination.relative_to(ROOT)}. Review the catalog and input mapping before use.")


if __name__ == "__main__":
    main()
