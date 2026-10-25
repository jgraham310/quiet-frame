# Quiet Frame

A Samsung **The Frame** adaptation of [Quiet Tizen](https://github.com/jss8649/quiet-tizen),
with configurable inputs and conservative preservation of Samsung's Art Mode.

**Frame compatibility is under development; no Frame model/firmware has been
validated by this fork yet.** Start with the [Frame setup guide](docs/10-frame.md).
The default device profile permits identification/preflight only. It cannot
deploy the launcher or generate cleanup plans. The original U8000F profile is
available only when explicitly selected.

The launcher now reads [tv.json](launcher/assets/tv.json): one to four HDMI
inputs, optional verified Art Mode/original Samsung Home app IDs, and up to
three dock apps. No source integers or Art Mode app IDs are guessed. Private
brightness/Game Mode controls default off, and Frame mode uses an Art Mode
tile instead of the original sleep timer. Native power-button behavior is
left to Samsung. Art Mode's settings, sensors and SmartThings must remain
available and be checked on the actual device.

The upstream project documents work performed on one **Samsung UN75U8000FFXZA (2025
U8000F)**. It includes **Quiet Home**, a native launcher with a colorful,
English-language interface, lightweight settings, local app cards and a
shortcut to native Bluetooth controller pairing.

The [upstream layout illustration](docs/quiet-home-preview.svg) shows the old
three-input U8000F design; it is not a screenshot of the adapted Frame UI.

It also includes targeted cleanup profiles, source-build tools and rollback
recipes. **It is a working case study with a reusable toolkit, not a universal
installer or a replacement operating system.**

## Give this repository to your coding agent

Clone the repository, open it in Codex, and use:

> Read README.md and AGENTS.md, then inspect the documentation before touching
> my TV. Read docs/10-frame.md. Help me adapt Quiet Frame to a TV I own. First identify its exact
> model, firmware and runtime, compare them with the tested profile, and show
> me any compatibility gaps. Keep HDMI, sound, networking, Bluetooth and
> accessibility, Art Mode, Art Store, sensors and SmartThings working. Prefer HDMI and minimize smart features; keep the
> streaming apps I choose. Back up my actual settings and prepare rollback
> before each change. Install and verify Quiet Home before assigning it to
> Home/startup or replacing the slow settings sidebar. Use the measured
> findings and known limitations rather than assuming every package is spyware
> or promising a particular speed improvement.

If your TV differs, begin with an inventory. A matching brand, year, Tizen
version or successful root check is **not** enough to establish launcher or
cleanup compatibility.

## What is here

| Component | What it does |
|---|---|
| [Quiet Home source](launcher/src/Home.cs) | Native .NET/NUI home, HDMI cards, app library and quick settings |
| [App catalog](launcher/assets/apps.json) | Example shortcuts for Netflix, YouTube, Prime Video, HBO Max, Disney+, Hulu, Spotify, Apple TV, Tubi, Luna and Xbox |
| [Frame configuration](launcher/assets/tv.json) | Verified input mappings and optional native shortcuts; customize with ignored `tv.local.json` |
| [Frame profile template](profiles/frame-template.json) | Inventory starting point, with no model, firmware or cleanup targets assumed |
| [Artwork tools](docs/06-artwork.md) | Vector/high-resolution artwork sources, optional local downloads and retained image views |
| [Cleanup profile](profiles/un75u8000ffxza-1300.9.json) | Separately selectable advertising, voice, context, smart-extras, sidebar and TV Plus groups |
| [Cleanup planner](tools/plan_cleanup.py) | Field-specific apply/restore SQL generated from your own fresh snapshot |
| [Access helper](tools/tv.py) | Explicit-target SDB preflight, temporary authenticated root, bounded transfers and session cleanup checks |
| [Recipes](recipes) | Snapshot, stop-marker, launcher, settings-bridge and restoration scripts |
| [Evidence](evidence/observations.json) | Sanitized observations and the limits of what was verified |

Quiet Home uses Tizen's existing display, audio, HDMI and application stack.
It can become the default Home/startup experience; Samsung's underlying OS
continues to run. The TV does not need a laptop running after installation.
Root access is reacquired from the computer when maintenance requires it.

## Upstream tested scope (U8000F only)

| Item | Recorded result |
|---|---|
| Model | `UN75U8000FFXZA` |
| Firmware | `T-KSU2EFAKUC-0090-1300.9` |
| Platform | Tizen 9.0, Linux 5.4.261, ARMv7; .NET runtime 6.0.9 |
| Temporary root | Authenticated UID/EUID 0; session staging cleaned; passwd/SDB key unchanged |
| Home/startup | Quiet Home launch verified after a full restart |
| Inputs and everyday controls | HDMI switching, volume and mute verified; native settings remain available |
| Controller | Native DualSense pairing and launcher navigation verified |
| Cleanup | Package flags and selected service-stop conditions checked; a subset survives restart |
| App preloading | Vendor refreshes can restore the preference; no permanent enforcement daemon |
| Netflix | More available memory after closing background apps; perceived input lag **not yet confirmed fixed** |

The upstream native launcher and underlying techniques were exercised on that TV.
The **generalized scripts in this public release were checked locally and
compiled where applicable; they have not been replayed end-to-end on a second
TV**. This matters especially for private Samsung APIs and registry schemas.

## Walkthrough

1. [Start with The Frame compatibility guide](docs/10-frame.md).
2. [Understand compatibility and inventory the TV](docs/01-inventory.md).
3. [Enable Developer Mode and check temporary access](docs/02-access.md).
4. [Take snapshots and apply selected cleanup](docs/03-cleanup.md).
5. [Build, install and assign Quiet Home](docs/04-launcher.md).
6. [Pair a DualSense using the TV's Bluetooth support](docs/05-controller.md).
7. [Customize apps, fetch artwork and keep it preloaded](docs/06-artwork.md).
8. [Diagnose slow streaming apps without overclaiming](docs/07-performance.md).
9. [Understand privacy findings](docs/08-privacy.md).
10. [Restore the original experience](docs/09-recovery.md).

Read [AGENTS.md](AGENTS.md) before using the tools. TV commands require a
specific address and a verified firmware declaration. All downloaded
proprietary references, local artwork, snapshots and session records stay
under ignored paths.

## Development

Host tools use Python 3.12+ and the standard library. Raster artwork conversion
optionally uses Pillow. Source builds accept the .NET 6 SDK or a newer stable
SDK when 6 is absent. CI checks SDK 6 and 10.0.302 in isolated installations.
The host SDK is separate from the TV's target runtime; building with SDK 10
does not make a `netcoreapp3.1` payload require .NET 10 on the TV.
Install Samsung's SDB separately.

Tizen and CLR version numbers are separate. The build helper also accepts
`--target-framework netcoreapp3.1` for an observed older CLR, with isolated
outputs and verified payload manifests. See the [2021 Frame notes](docs/10-frame.md).

```sh
python3 -m unittest discover -s tests -v
python3 tools/build.py payloads
# After obtaining the four private Tizen reference assemblies:
python3 tools/build.py launcher --framework .local/tv-framework
```

GitHub Actions runs the offline tests and builds the open-source access
payloads, app-catalog tests and Frame-configuration tests. The NUI launcher build needs Samsung reference
assemblies and is deliberately not built from redistributed SDK files.

## Credits

The visual design adapts [Free My TV](https://github.com/simbasjungles/free-my-tv);
the temporary archive-launcher access route comes from
[samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root).
This is a native Tizen port of the visual approach, not an installation of
the Android launcher. See [NOTICE.md](NOTICE.md) and
[provenance](docs/provenance.md) for exact commits, licenses and local changes.

Original project code is MIT-licensed. Third-party fonts, symbols and access
code retain their own licenses. No Samsung firmware, stock app binaries,
private TV backups or publisher app artwork is included.
