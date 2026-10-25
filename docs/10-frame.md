# Adapt Quiet Frame to your TV

The Frame uses Tizen too, but the original U8000F's firmware, native APIs,
source integers and package layout are not a Frame compatibility profile.
This fork provides a configurable launcher and guarded host tools; it does
not yet provide a validated Frame installer or promise root access on a
particular Frame generation.

## Identify the exact target

Record the model code and **complete software version** from Settings →
Support → About This TV. Do not share the serial number, MAC address or QR code.
Year/size alone cannot establish runtime compatibility, particularly after
firmware upgrades. Samsung publishes [TV model groups](https://developer.samsung.com/smarttv/develop/specifications/tv-model-groups.html),
but inspect the actual runtime and capabilities too.

### 2021 LS03A family

Samsung lists LS03A in its 2021 `21TV_PREMIUM1` group with a Tizen 6.0
platform baseline. That is a different generation from the upstream Tizen 9
case study. A firmware version is not proof of its current CLR version or
of archive-route access. **Tizen 6.0 does not mean .NET 6.0.** Keep the retail
model code separately if SDB reports an internal platform/model identifier;
the private profile's `model` gate must match the actual SDB output exactly.
Preserve the full About-screen firmware string, including suffixes, in your
private notes/profile; quote it when passing `--firmware` to the shell.

With Samsung's SDB separately installed and Developer Mode authorized for
your computer, use only the owner's explicit TV address:

```sh
python3 tools/tv.py --host YOUR_TV_IPV4 identify
python3 tools/tv.py --host YOUR_TV_IPV4 doctor
```

Replace `YOUR_TV_IPV4`; neither command scans the network. `identify` reads
the SDB device identity only. `doctor` checks archive-route prerequisites,
without requesting root. Firmware remains an operator observation from the
About screen, not something this helper independently verifies. A successful
doctor result is not launcher/cleanup compatibility proof.

Copy `profiles/frame-template.json` into ignored `.local/frame.json`. Enter
the exact SDB model and About-screen firmware; leave `allow_mutation` false
and `groups` empty. Do not substitute the original U8000F firmware string.
After inspecting preflight and building the access payloads, an exact private
profile can be used for temporary-root testing and read-only collection:

```sh
# Choose the framework printed by doctor. For example, ONLY if it reports 3.1:
python3 tools/build.py payloads --target-framework netcoreapp3.1
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' root-check
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' inventory
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' platform
```

For an observed runtime family of `6.0`, build with `--target-framework net6.0`.
The build SDK on your computer is independent of this target. If only a newer
SDK such as 10.0.302 is installed, `global.json` accepts it; installing SDK 6
alongside it is not required. Check `dotnet --version` from this checkout if
SDK selection fails. Keep `--target-framework netcoreapp3.1` for an observed
3.1 TV even when the Mac uses SDK 10.
The helper chooses the matching output directory and verifies its build manifest,
runtime configuration and file digests before requesting root. It refuses a
stale/unrecorded or mismatched build. Merely generating a 3.1 runtimeconfig for
a .NET 6 DLL does not retarget that DLL. The separate 3.1 build prevents that
mistake, but successful compilation alone does not prove this TV can execute it.

These commands still use the vendored temporary-root route; success is not
assumed. Inventory records stay in `.local/sessions/`. A missing
`db/appfw/startup_appid` is recorded as absent without creating it. Other
preference errors and incompatible schemas still fail; an absent preference
does not establish an alternate startup mechanism. The `platform` command
prints focused read-only application entry points, Home/Art key filters and
framework/native-library paths, and saves the same private session record.
It helps identify differences when the original Bixby Promotion/QuickLaunch
containers are missing; it does not choose or replace another container.
Review the output privately rather than posting it to a public issue.
`pull` is also available for bounded private
reads with the exact profile; generic `exec` and `push` remain blocked while
`allow_mutation` is false.

## Preserve native Frame functions

Samsung documents the normal Power-button path between TV and Art Mode,
plus motion/light behavior and SmartThings controls in its
[Art Mode guide](https://www.samsung.com/us/support/answer/ANS10005239/).
Check the actual TV's Power Button setting because behavior varies. Quiet
Home does not intercept Power, issue power toggles, upload art, change sensor
settings or implement Samsung's Art Store protocol. The optional `ArtModeAppId`
shortcut is an application launch, not a claim that every Frame exposes a
launchable Art Mode application. Validate the actual result; otherwise leave
it null and use the Samsung remote/native UI.

Keep Art Mode/Art Store, motion/light/power services, native Home and settings,
SmartThings and selected apps. Discover **actual** app IDs and dependencies;
names alone do not establish what a service does. Add discovered dependencies
to the private profile's `protected_app_ids`. The cleanup planner rejects
essential containers and conservative Art/ambient/sensor/power/SmartThings/
context name matches, even under renamed groups. These checks are not a
complete dependency map and do not audit arbitrary shell commands.

The U8000F `smart-extras`, `context` and `light-shell` groups are rejected for
Frame profiles. Do not import the other groups wholesale either. A future
Frame cleanup profile must contain only individually validated targets and
requires `allow_mutation: true`; leave the template with no targets. Reuse
the existing snapshot-based, field-specific apply/restore planner only after
validating the target's registry schema and dependencies.

## Configure and validate the launcher

Copy `launcher/assets/tv.json` to ignored `launcher/assets/tv.local.json`.

| Setting | Required evidence |
|---|---|
| `Family` | `frame` for this fork; `u8000f` only for the original controls |
| `Inputs` | One to four labels and actual source IDs; `null` leaves a card unconfigured |
| `ArtModeAppId` | Optional native app ID whose launch actually opens Art Mode; otherwise `null` |
| `NativeHomeAppId` | Original Samsung Home ID saved before any routing changes; otherwise `null` |
| `DockAppIds` | Up to three verified app IDs also present in your local app catalog |
| `EnablePrivateSettings` | Default `false`; enable only after private brightness/Game Mode APIs are validated |

Obtain the matching private NUI/framework references and inspect source IDs
using [the launcher guide](04-launcher.md). Do not assume the .NET 6 build or
the Bixby Promotion/QuickLaunch containers exist on every Frame. The build
helper accepts `--target-framework net6.0` (default) or `netcoreapp3.1`, selected
only from observed runtime evidence. For the latter, build output lives in
`.local/build/netcoreapp3.1/` and launcher packages in `.local/package-netcoreapp3.1/`.
Use matching private reference assemblies; older NUI APIs may still need source
adaptation and the complete launcher has not been compiled for a Frame yet.
`tv.local.json` overrides the packaged `tv.json`; local files stay ignored.

Before enabling mutation, establish runtime/assembly compatibility, package
entry points, owners/labels, user IDs, source IDs, native APIs, selectors,
consistent snapshots and specific inverse operations. The existing install/
bridge scripts remain U8000F recipes. Do not run them just because the TV is
a Frame or root works. Adapt them only to observed matching evidence.

Install and manually test the UI before changing Home. Check full boot and
standby/wake separately, Art Mode enter/exit, remote Power/long-press behavior,
motion/light settings, native Home/settings, SmartThings, all configured HDMI
ports (including picture/audio/CEC), chosen apps and the existing recovery
path. Do not call the Frame port validated until those hardware tests pass.

## Offline checks

```sh
python3 -m unittest discover -s tests -v
dotnet run --project tests/LauncherConfigTests.csproj -- launcher/assets/tv.json
dotnet run --project tests/CatalogTests.csproj -- launcher/assets/apps.json
```

These checks cover profile restrictions, protected cleanup targets, SQL
rollback/drift, source mapping and configuration fallbacks without claiming
that private Samsung APIs or actual Art Mode behavior have been tested.
CI also compiles access payloads and shared launcher logic against .NET Core
3.1 references. It does not run the native UI or establish execution on a 3.1 TV.
