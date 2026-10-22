"""Model-specific compatibility gates; a template never authorizes TV changes."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "profiles/frame-template.json"
ESSENTIAL_APPS = {
    "com.samsung.tv.bixby-promotion", "com.samsung.tv.quicklaunch",
    "org.tizen.menu", "org.tizen.tv-viewer",
}
# Conservative name-based exclusions, NOT a complete Art Mode dependency map.
FRAME_FEATURE = re.compile(
    r"(^|[._-])(art|artmode|artstore|ambient|sensor|power|aov|smartthings|context)([._-]|$)",
    re.IGNORECASE,
)
FRAME_BLOCKED_GROUPS = {"smart-extras", "context", "light-shell"}


def load_profile(path=DEFAULT_PROFILE):
    profile = json.loads(Path(path).read_text())
    if profile.get("profile_version") not in (1, 2):
        raise ValueError("Unsupported device profile version.")
    if profile.get("family") not in ("frame", "u8000f"):
        raise ValueError("A device profile must declare its family (frame or u8000f).")
    if type(profile.get("allow_mutation")) is not bool:
        raise ValueError("A device profile must declare allow_mutation as a boolean.")
    if not isinstance(profile.get("groups"), dict):
        raise ValueError("A device profile must contain a groups object.")
    return profile


def check_identity(model, firmware, profile, *, mutation=False):
    if not all(isinstance(profile.get(k), str) and profile[k].strip() for k in ("model", "firmware")):
        raise ValueError("This is an inventory template. Record the exact model and firmware "
                         "in a separate .local/ profile before using root access.")
    if model != profile["model"]:
        raise ValueError(f"Unsupported model {model!r}; stop and investigate a separate profile.")
    if firmware != profile["firmware"]:
        raise ValueError("Supply --firmware with the exact version read from About This TV. "
                         "It must match the selected profile; do not guess this value.")
    if mutation and not profile["allow_mutation"]:
        raise ValueError("This profile allows inventory only. Validate this model's runtime, "
                         "containers, APIs and rollback before enabling allow_mutation.")


def cleanup_ids(profile, groups):
    # Planning is offline, but do not turn an unverified template into an installer.
    check_identity(profile.get("model"), profile.get("firmware"), profile, mutation=True)
    ids = []
    protected = ESSENTIAL_APPS | set(profile.get("protected_app_ids", []))
    for group in groups:
        if profile["family"] == "frame" and group in FRAME_BLOCKED_GROUPS:
            raise ValueError(f"{group}: the U8000F group is not portable to The Frame. "
                             "Use individually reviewed targets in a separate Frame group.")
        if group not in profile["groups"]:
            raise ValueError(f"Unknown group: {group}")
        targets = profile["groups"][group]["app_ids"]
        if not isinstance(targets, list) or not targets:
            raise ValueError(f"{group}: no verified cleanup targets.")
        for app in targets:
            if not isinstance(app, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", app):
                raise ValueError("Invalid application ID.")
            if app in protected or (profile["family"] == "frame" and FRAME_FEATURE.search(app)):
                raise ValueError(f"Protected application: {app}. Preserve native/Frame features.")
            ids.append(app)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Select nonempty groups without duplicate application IDs.")
    return ids
