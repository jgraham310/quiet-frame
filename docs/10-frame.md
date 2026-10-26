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
After pulling changes to the access payload source, rebuild payloads for that
same TV target before opening another temporary-root session.
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

For native source IDs and the current main-operation Home handler, build the
standalone diagnostic (no Samsung reference DLLs required) and run its fixed
read-only mode:

```sh
python3 tools/build.py probe --target-framework netcoreapp3.1
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' sources
```

Select the framework printed by `doctor`, as with the access payloads. `sources`
requires the diagnostic's recorded build manifest, runtime configuration and
file digests. It stages Probe inside the temporary root session's own directory,
checks transfer digests, and executes it without arguments. It never selects
Probe's `set-home` branch or changes inputs. Session cleanup removes both
diagnostic files. Native API errors remain diagnostic results, not verified
source mappings. No generic mutation permission is needed for this command.

Before adapting installation, `containers` reads package registry schemas,
owners/security-label listings, and bounded manifest/runtime-configuration
samples from existing managed packages. These samples include native Home
and Art Mode for comparison; they are not replacement targets. The command
does not launch apps, change permissions, register packages or alter files:

```sh
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' containers
```

If AdPlayer is being evaluated as a possible trial container, append
`--adplayer-details` to inspect its actual entry/cache files, hashes, per-user
application records, explicit dependency rows and launch-tool help. This is
still read-only. An installed manifest and file ownership alone do not prove
that a package can safely host the launcher or establish its launch user.

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
| `Inputs` | Zero to four labels and actual source IDs; `[]` opens directly to Apps, and `null` source IDs leave individual cards unconfigured |
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
adaptation. The owner has reported successful Home, QuickLaunch and Probe builds
against copied Frame references; installation and visible UI checks are pending.
`tv.local.json` overrides the packaged `tv.json`; local files stay ignored.

For a TV with no HDMI devices connected, keep `Inputs: []`. Apps becomes the
Home page, only Apps/Settings tabs appear, and Settings Back returns to Apps.
The toolbar keeps Samsung Home accessible once its shortcut has been verified;
Art Mode remains available from Settings and the native remote. No source
probe is required for this setup. Add verified input entries later to restore
the Inputs page and its original Back-to-input behavior.

An experimental `--home-assembly AdPlayer` build variant emits `AdPlayer.dll`,
its generated runtime configuration/dependency file and resources into a
separate `.local/package-netcoreapp3.1-AdPlayer/` folder for a 3.1 target. It
does not include the original QuickLaunch bridge. This option builds only;
it is not an AdPlayer installer and does not approve changing that package.
The assembly's compiled identity requires an explicit `quiet_page` value of
`home`, `apps` or `settings` before initializing/showing Quiet Home. Unmarked
requests hide the window and exit instead of being treated as Home requests.
The BixbyPromotion variant retains its original launch behavior.

Before a trial, verify actual entry/AOT files and launch user, record original
hashes/owners/labels, create consistent registry snapshots and preserve original
assembly/runtime/cache files both on the TV and on the computer. Prepare the
specific inverse operations before replacing anything. Keep Home/startup and
all native settings/Art Mode packages intact during the manual trial. Vendor
runtime configurations targeting .NET Core 2.0 do not change the observed 3.1
runtime or justify retargeting the new build to 2.0.

After a successful detailed preflight, create recovery copies with a unique
name before any trial installation:

```sh
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' backup-adplayer --name adplayer-01
```

This dedicated preparation command can use an inventory-only profile. It reads
the two original hashes from the latest matching, clean local preflight log
and refuses changed originals or an existing backup. It copies the entry DLL,
runtime configuration and entry native image with metadata into a private TV
recovery directory, takes individual consistent SQLite backups, records Home
preferences and SDK-user evidence, and writes a restoration scope/plan.
It never changes the installed package, preload flags or Home routing.

The archive is transferred through the authenticated root-agent file channel
from its owned staging directory, with SHA-256 validation and a 4 MiB bound.
The local copy is saved at `.local/backups/NAME/backup.tar.gz`; the TV copy
stays under `/opt/usr/share/quiet-frame-backups/NAME/`. Archive copies contain
private binaries/data and must not be published. The TV copy preserves original
SMACK attributes; file metadata is also recorded inside the archive.
If only transfer failed after TV preparation completed, repeat the same command
with `--fetch-existing`. It verifies/retrieves the completed copy without
overwriting originals. Incomplete backups remain for inspection; never delete
one merely to make a retry succeed. If copying and snapshots completed but
finalization stopped (for example, an older recipe required an unavailable
`cmp` utility), use `--resume-incomplete` with the same name. This checks all
retained copies, snapshots, source hashes and metadata, then finishes only
the missing finalization steps. It never re-copies originals or refreshes
snapshots. Missing state, changed data or partially written finalization files
stop for inspection. Content comparisons use the TV's verified SHA-256 utility.
A completed backup does not prove a
successful native UI trial. The dedicated trial workflow below generates
an executable inverse for the exact planned files before installation.

The SDK connection's UID and owners of `/run/user/` directories do not by
themselves establish the native UI's launch user. With Samsung Home visible,
collect the selected running native UI process identities:

```sh
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' launch-context
```

This fixed read-only check matches complete process arguments for native Home,
Art, settings and AdPlayer, then prints only those known arguments, PID,
UID/GID fields and SMACK context. It does not print other arguments or process
environments, and never launches or stops an application. An empty result
remains an observation; it does not select a default UID. Keep generic mutation
disabled while launch context and the specific executable inverse are prepared.

### Experimental manual AdPlayer trial

This separate workflow is for an explicitly inspected AdPlayer container,
verified recovery archives on both the TV and computer, and matching clean
`launch-context` evidence for native Home and Art. It is not a generally
validated Frame installer. The older U8000F recipes remain incompatible.
These dedicated commands require the exact private Frame profile and a pinned
private trial plan; they do not enable generic `exec`/`push` or cleanup groups.

Rebuild with the matching private references. The AdPlayer variant now also
builds a short-lived standalone app-control helper and records package hashes:

```sh
python3 tools/build.py launcher --framework .local/tv-framework --target-framework netcoreapp3.1 --home-assembly AdPlayer
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' adplayer-trial prepare --name trial-01 --backup adplayer-01
```

Use the actual CLR target, as above. Preparation checks the local recovery
archive against a clean authenticated session, verifies its original-file
hashes and the recorded build, and creates an immutable plan/archive/inverse
under `.local/trials/NAME/`. It filters catalog shortcuts against enabled IDs
in the recovery snapshot; it does not uninstall apps or modify the source
catalog. The first trial requires `Inputs: []`, private settings off and native
Home/Art shortcuts unassigned.

Preparation stages only a bounded, checksum-verified archive inside the root
session's own directory, retains the pinned trial under
`/opt/usr/share/quiet-frame-trials/NAME/`, and verifies the current native UI
UID/GID. It resolves that exact account and runs the helper through `runuser`
with only the session runtime directory and, when present, the native UI's
session-bus address. Other process environment values are not copied or
printed. The helper independently checks all four real/effective user/group
IDs and creates/destroys an app-control handle without sending a launch request.
Preparation leaves installed files, preload and Home routing unchanged.

After preparation succeeds, the explicit install and launch operations are:

```sh
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' adplayer-trial install --name trial-01
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' adplayer-trial launch --name trial-01
```

| Trial change | Specific inverse |
|---|---|
| Replace `bin/AdPlayer.dll` and its runtime configuration | Restore the saved originals with their ownership, mode and SMACK labels |
| Add `bin/AdPlayer.deps.json` and `res/quiet-home` | Remove only the planned, hash-verified additions; refuse unexpected paths |
| Move only `.native_image/AdPlayer.ni.dll` outside the execution path | Restore the saved entry image; retain other native libraries/images |
| Set only AdPlayer's `app_preload` from `true` to `false` | Restore only that field to the recorded original value |

Install refuses a running AdPlayer, changed originals/metadata, incompatible
registry flags, existing resources/deps or a previously started installation.
It prepares all resources off to the side, checks labels and permissions,
then uses individual atomic renames for installed paths. The full operation
is not one atomic transaction. Other app files, account data and native
Home/startup, Art, power and settings routing are outside its scope.

Launch sends the compiled `quiet_page=home` marker to AdPlayer through the
native app-control API. A successful API result means a request was submitted;
the owner must still verify the visible UI, remote, streaming apps, volume,
native settings and return to Samsung Home. Keep the TV on until each root
session reports normal cleanup. Restart/standby testing comes later.

Undo with the same exact profile and trial name:

```sh
python3 tools/tv.py --host YOUR_TV_IPV4 --profile .local/frame.json --firmware 'YOUR_EXACT_FIRMWARE' adplayer-trial restore --name trial-01
```

Restore checks the pinned controls, retained backup, current hashes and metadata,
and selected registry fields before stopping only AdPlayer under the recorded
UID. It accepts the known mixture of original/new paths left by an interrupted
install and can resume interrupted restoration. Partial temporary copies are
retained outside the package for inspection. Unrelated registry changes remain
intact; no snapshot replaces a live database. A completed old restore refuses
to overwrite a later trial. The on-TV `restore.sh` is also pinned to the saved
control manifest, for reviewed recovery through an existing root session.

If any phase fails, inspect its private log and use this inverse for an
installation that started. Do not retry install, remove guards, delete the
first backup or overwrite a trial name. A drift refusal requires inspecting
the actual changed state. The tests exercise these operations on temporary
files/databases with native APIs stubbed; they do not establish TV execution.

The launcher uses the application's existing window and explicitly aliases
filesystem paths to avoid NUI's own `Path` type. A compatibility helper inspects
the loaded corner-radius property to support either a scalar or a four-corner
vector without tying that choice to the CLR target. Missing native border
properties are optional decoration; the app grid has an SVG focus outline and
other controls retain scale/label focus. Image loading uses the framework's
default sampling rather than requiring newer sampling enums/properties.
Synthetic helper checks cover both radius shapes, but the full native build
must still use the owner's matching assemblies and be tested on the TV.

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
