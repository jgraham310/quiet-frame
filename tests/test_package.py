import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from fetch_artwork import convert, destination
from build import package_launcher


class PackageTests(unittest.TestCase):
    def test_adplayer_package_uses_its_own_entry_and_omits_legacy_bridge(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            builds, assets, output = root / "build", root / "assets", root / "package"
            assets.mkdir()
            (assets / "tv.json").write_text('{"Family":"frame","Inputs":[]}')
            (assets / "apps.json").write_text('[]')
            for name in ("AdPlayer.dll", "AdPlayer.runtimeconfig.json", "AdPlayer.deps.json"):
                path = builds / "Home-AdPlayer" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            probe = builds / "Probe/Probe.dll"
            probe.parent.mkdir()
            probe.write_bytes(b"synthetic probe")
            package_launcher(builds, assets, output, "AdPlayer")
            self.assertEqual((output / "AdPlayer.dll").read_text(), "AdPlayer.dll")
            self.assertTrue((output / "AdPlayer.runtimeconfig.json").exists())
            self.assertTrue((output / "AdPlayer.deps.json").exists())
            self.assertFalse((output / "BixbyPromotion.dll").exists())
            self.assertFalse((output / "QuickLaunch.dll").exists())
            self.assertEqual(json.loads((output / "quiet-home/tv.json").read_text())["Inputs"], [])

    def test_local_configuration_is_packaged_and_clean_rebuild_restores_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            builds, assets, output = root / "build", root / "assets", root / "package"
            assets.mkdir()
            for path in ("Home/BixbyPromotion.dll", "QuickLaunch/QuickLaunch.dll", "Probe/Probe.dll"):
                file = builds / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"synthetic build fixture")
            (assets / "tv.json").write_text('{"Family":"frame"}')
            (assets / "tv.local.json").write_text('{"Family":"frame","Inputs":[{"Name":"Local input"}]}')
            (assets / "apps.json").write_text("[]")
            (assets / "apps.local.json").write_text('[{"Name":"Local app"}]')
            package_launcher(builds, assets, output)
            packed = output / "quiet-home"
            self.assertEqual((packed / "tv.json").read_bytes(), (assets / "tv.local.json").read_bytes())
            self.assertEqual((packed / "apps.json").read_bytes(), (assets / "apps.local.json").read_bytes())
            self.assertFalse((packed / "tv.local.json").exists())
            self.assertFalse((packed / "apps.local.json").exists())
            (assets / "tv.local.json").unlink()
            package_launcher(builds, assets, output)
            self.assertEqual((packed / "tv.json").read_bytes(), (assets / "tv.json").read_bytes())

    def test_catalog_assets_exist_and_ids_are_unique(self):
        catalog = json.loads((ROOT / "launcher/assets/apps.json").read_text())
        self.assertEqual(len({a["Id"] for a in catalog}), len(catalog))
        for entry in catalog:
            asset = entry["Asset"]
            self.assertNotIn("..", asset)
            self.assertTrue((ROOT / "launcher/assets" / asset).is_file(), asset)
        self.assertEqual(sum(bool(a.get("Utility")) for a in catalog), 1)

    def test_profile_has_no_duplicate_app_ids_or_essential_containers(self):
        profile = json.loads((ROOT / "profiles/un75u8000ffxza-1300.9.json").read_text())
        ids = [app for group in profile["groups"].values() for app in group["app_ids"]]
        self.assertEqual(len(ids), len(set(ids)))
        for essential in ("com.samsung.tv.bixby-promotion", "org.tizen.menu", "com.samsung.tv.quicklaunch"):
            self.assertNotIn(essential, ids)

    def test_shell_syntax(self):
        for path in (ROOT / "recipes").glob("*.sh"):
            subprocess.run(["sh", "-n", str(path)], check=True, capture_output=True)

    def test_artwork_destinations_and_active_svg_rejected(self):
        with self.assertRaises(ValueError):
            destination("../elsewhere.svg")
        entry = {"name": "Example", "asset": "app-icons/example.svg",
                 "catalog": {"Width": 100, "Height": 50}}
        valid = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><path d="M0 0"/></svg>'
        self.assertEqual(ET.fromstring(convert(valid, entry)).get("width"), "100")
        for data in [
            b'<svg><script>alert(1)</script></svg>',
            b'<svg><image href="https://example.com/image.png"/></svg>',
            b'<svg onload="alert(1)"/>',
            b'<!DOCTYPE svg [<!ENTITY x "x">]><svg/>',
        ]:
            with self.assertRaises(ValueError):
                convert(data, entry)

    def test_relative_document_links_resolve(self):
        for doc in [ROOT / "README.md", ROOT / "NOTICE.md", *sorted((ROOT / "docs").glob("*.md"))]:
            for link in re.findall(r"\[[^\]]*\]\(([^ )]+)(?: [^)]*)?\)", doc.read_text()):
                if "://" in link or link.startswith("#"):
                    continue
                path = link.split("#", 1)[0]
                self.assertTrue((doc.parent / path).exists(), f"{doc.name}: {link}")


if __name__ == "__main__":
    unittest.main()
