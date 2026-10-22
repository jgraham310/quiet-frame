import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from device_profiles import load_profile, cleanup_ids


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.profile.update(model="SYNTHETIC_FRAME", firmware="SYNTHETIC_VERSION", allow_mutation=True)
        self.profile["groups"] = {"reviewed": {"app_ids": ["example.optional"]}}

    def test_frame_template_and_inventory_profile_cannot_generate_cleanup(self):
        with self.assertRaises(ValueError):
            cleanup_ids(load_profile(), ["advertising"])
        self.profile["allow_mutation"] = False
        with self.assertRaises(ValueError):
            cleanup_ids(self.profile, ["reviewed"])

    def test_exact_reviewed_targets_and_dependency_protection(self):
        self.assertEqual(cleanup_ids(self.profile, ["reviewed"]), ["example.optional"])
        self.profile["protected_app_ids"] = ["example.optional"]
        with self.assertRaisesRegex(ValueError, "Protected"):
            cleanup_ids(self.profile, ["reviewed"])

    def test_frame_features_are_preserved_even_if_group_is_renamed(self):
        for app in ("org.tizen.menu", "org.tizen.tv-viewer", "com.samsung.tv.bixby-promotion",
                    "com.samsung.tv.artmode", "com.samsung.tv.art-store", "com.samsung.tv.ambient-sound",
                    "com.samsung.tizen.smartthings-client", "com.samsung.tv.sensor-service",
                    "com.samsung.tv.aov-dashboard", "com.samsung.tv.power-service",
                    "com.samsung.tv.context-aware-service"):
            with self.subTest(app=app):
                self.profile["groups"]["reviewed"]["app_ids"] = [app]
                with self.assertRaisesRegex(ValueError, "Protected"):
                    cleanup_ids(self.profile, ["reviewed"])

    def test_legacy_broad_groups_cannot_be_imported_as_frame_groups(self):
        for group in ("smart-extras", "context", "light-shell"):
            self.profile["groups"][group] = {"app_ids": ["example.optional"]}
            with self.assertRaisesRegex(ValueError, "not portable"):
                cleanup_ids(self.profile, [group])

    def test_legacy_profile_remains_explicitly_usable(self):
        legacy = load_profile(ROOT / "profiles/un75u8000ffxza-1300.9.json")
        self.assertEqual(len(cleanup_ids(legacy, ["smart-extras"])), 11)
        self.assertEqual(len(cleanup_ids(legacy, list(legacy["groups"]))), 54)

    def test_invalid_empty_or_duplicate_targets_are_rejected(self):
        for targets in ([], ["example.optional", "example.optional"], ["bad';DROP TABLE x"]):
            profile = copy.deepcopy(self.profile)
            profile["groups"]["reviewed"]["app_ids"] = targets
            with self.assertRaises(ValueError):
                cleanup_ids(profile, ["reviewed"])
        with self.assertRaises(ValueError):
            cleanup_ids(self.profile, [])


if __name__ == "__main__":
    unittest.main()
