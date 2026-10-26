# Provenance and verification scope

## Original device work

The findings were compiled from local inspection, build/deployment records,
registry snapshots, post-restart checks and owner feedback collected
2026-10-19 through 2026-10-20. Private originals remain outside this repository.
No serial, network address, account identity, original application binary,
raw TV log or screen photo is needed to reproduce the findings.

[observations.json](../evidence/observations.json) contains a deliberately
small sanitized record. It is an observation summary, not an independently
reproducible benchmark dataset.

## Access tooling

Source: [chris-ritsen/samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root/tree/4ad2c4d3b0d0e0da4b5b7ebe4a787e94596f416b),
commit `4ad2c4d3b0d0e0da4b5b7ebe4a787e94596f416b`, Unlicense.

Only the archive-route support modules and two .NET payload projects are
vendored. The QN90B/QN90F kernel exploits, continuous host controller,
firmware-key tooling and unrelated payloads are not bundled.
`resources.py` retains upstream profile names, but this toolkit explicitly
builds only the two common access payloads, now separately targetable to .NET 6
or .NET Core 3.1. No additional exploit route was added for the Frame fork.

The original local change to the copied access code is in `archive_root.py`:
if Samsung's host returns the exact `Unknown option --list-runtimes` error,
resolve `/usr/share/dotnet.tizen/netcoreapp`, require `libcoreclr.so` and
`System.Private.CoreLib.dll`, then derive the runtime version from that path.
Other preflight errors still fail. This fallback was used on the actual TV.

The Frame fork additionally accepts an optional expected runtime family in
`probe`. It refuses a change between the wrapper's payload selection and
probe's own preflight before opening a root callback server or staging files.
The wrapper checks generated runtime configurations and build-manifest digests
before selecting a payload directory. These additions have offline tests;
they are not evidence that temporary root works on any Frame firmware.

The new `tools/tv.py` wrapper adds explicit model/declared-firmware gating,
private local storage, bounded checksum-verified file transfer and reviewed
single-command execution. Those generalized conveniences were locally
tested; they are not a claim of end-to-end testing on additional hardware.

Read-only inventory now records the specific missing-startup-preference
diagnostic without creating that preference, while preserving other failures.
The fixed `platform` queries collect candidate managed entry points, Home/Art
key filters and framework paths without enabling generic mutation commands.
Synthetic tests cover existing/missing/error preference responses and metadata
queries on a registry without the upstream replacement containers.

The `sources` wrapper mode runs the existing native diagnostic with no arguments
inside the temporary root session's staging directory. Its standalone build
has a framework-matched hash manifest; transfers are checked before execution,
and normal session cleanup also removes the diagnostic files. This mode rejects
custom commands/arguments and never selects Probe's mutating `set-home` branch.
The archive-route library accepts this optional diagnostic directory; generic
mutation permissions in the wrapper remain unchanged.

The fork also changes the root agent's process launcher to pass `/bin/sh`,
`-c` and the complete command through `ProcessStartInfo.ArgumentList`, instead
of manually escaping an `Arguments` string. This preserves shell backslashes,
quotes and newlines across runtime argument parsing. CI exercises the actual
agent execution method, including the complete generated platform script with
synthetic TV utility responses, on its host runtimes and compiles the same
test against .NET Core 3.1 references. This host test does not substitute for
running the rebuilt payload on the TV's runtime.

## Launcher and design

The C# launcher, app catalog, native settings bridge and Probe were developed
for the tested Tizen device. The public source retains the tested native
architecture, with a streaming-app dock shortcut and redistributable
placeholders in the public catalog.

Visual reference: [simbasjungles/free-my-tv](https://github.com/simbasjungles/free-my-tv/tree/73409804e5085e720dccea9ab95078a515cae098),
commit `73409804e5085e720dccea9ab95078a515cae098`, MIT. The port adapts layout,
palette, font treatment and focus/dock proportions. It does not run Android
code on Tizen. Inter and Material Symbols licenses are included separately.

Publisher logos remain optional local downloads. High resolution was preferred
over invented vectors for artwork such as the translucent Xbox mark. The
download manifest is an attribution/source record, not a license grant.

## What local validation establishes

The native compilation statements below describe upstream U8000F validation,
not a build of the changed Frame UI. The Frame fork separately tests host
tools and shared C# logic; its native UI still needs matching private references
and hardware validation. `global.json` uses a stable .NET 6 SDK when available
and accepts a newer major SDK when 6 is absent. CI uses isolated SDK 6 and
10.0.302 installations and verifies the selected SDK before building both
TV runtime targets. Host test execution may roll forward to the installed
host runtime; the TV payload runtime configurations and target checks remain
separate.

NUI source adaptations also address the owner's compiler diagnostics: use
the application's existing window, disambiguate filesystem paths, adapt scalar
and vector corner-radius properties, avoid requiring newer image sampling
members, and provide an SVG app-focus outline when native border properties
are absent. CI exercises the compatibility helper against synthetic old/new
API shapes. Those fixtures contain no Samsung implementation and do not prove
that the full native UI compiles or renders on the owner's TV.

The owner subsequently reported successful .NET Core 3.1 compilation of Home,
QuickLaunch and Probe on their Mac, using the four framework DLLs copied from
their Frame. This is reported build evidence, not a cloud build with proprietary
references or proof that the UI has run on the television. Device-specific
identity and inventory stay in private records; installation, input routing,
Art Mode behavior and visible UI validation are still pending.

Streaming-only configuration now accepts an empty input list, starts in Apps,
omits Inputs navigation and returns Settings Back to Apps. Shared configuration
tests exercise both zero-input and explicitly mapped-input modes. The fixed
`containers` reader collects package schemas, labels and bounded configuration
samples without approving replacement of those packages. A temporary-filesystem
test verifies that its inspection leaves the sampled files unchanged.

An experimental AdPlayer assembly variant now uses separate build/package
directories, carries its generated runtime/dependency files and omits the
U8000F QuickLaunch bridge. The compiled assembly identity gates initialization
on an explicit Quiet Home app-control marker; shared tests exercise accepted
and rejected requests. Detailed read-only inspection collects entry/cache
hashes and user records before any backup/install plan. These changes do not
establish AdPlayer as a validated Frame container or constitute installation.

The owner reported successful compilation of the isolated AdPlayer variant
against their copied references. Detailed inspection identified its original
entry/native image and preload state, while the per-user override table was
empty; no launch UID is inferred from that absence.

Dedicated AdPlayer backup preparation now pins original hashes to a matching
clean preflight record, preserves selected originals on the TV, makes SQLite
backups and transfers a bounded archive to private local storage. The archive
route supports an optional command factory scoped to its generated session
directory and collects only simple artifact filenames through the existing
authenticated file protocol, followed by normal cleanup. Tests exercise the
whole backup recipe on temporary files/SQLite databases, refusal to overwrite
or accept changed originals, and scoped file collection. These tests do not
establish TV-side backup or installation success before the owner runs them.

Owner feedback established that this Frame lacks `cmp`. Backup comparisons now
use SHA-256 without that dependency. Incomplete-copy finalization has an explicit
resume mode that validates and retains the first original files/snapshots.
Tests simulate interruption before finalization, verify preserved bytes and
modification times on resume, and reject a damaged retained copy.

The owner subsequently reported successful resume, verified recovery archives
on their computer and TV, and clean temporary-root teardown. Installed originals
and Home routing were unchanged. The SDK UID differs from a user runtime
directory's owner, so neither is silently selected as the native launch UID.
A fixed `launch-context` reader now reports selected live native UI process
identities without dumping other arguments or environments. Synthetic proc
fixtures check exact-argument matching, exclusion of the reader's own shell,
absence of unrelated secrets, and an explicit empty result. Actual native
launch identity, executable trial/restore and visible UI validation remain pending.

Subsequent owner output identified native Home and Art running with the same
real/effective UID/GID, distinct from the SDK account, with AdPlayer absent
from the selected live processes. That identity evidence now gates a dedicated
manual-trial plan. Device-specific numeric identities remain private.

The trial generator pins matching recovery/build evidence and prepares an
immutable private archive, explicit file/preload changes and an executable
inverse before installation. A short-lived app-control sender checks its user
context, requires an explicit Quiet Home marker, propagates native failures and
destroys created handles. Preparation can test handle creation without launch.
The transport stages bounded extra files only inside its owned root session,
verifies digests and retains normal cleanup checks.

Synthetic tests exercise complete preparation/install/launch/restore, the
pinned archive entry path, interruption at each mutation phase and during
restoration, preservation of first backups/unrelated registry data, metadata
and path drift refusals, wrong user IDs, and refusal of an old inverse after
a newer trial. Helper API tests cover failures/exceptions and handle cleanup
without Samsung libraries. These checks are not evidence of a visible native
UI or successful helper execution on the actual TV; those remain pending.

- Native launcher, bridge, Probe and root payload source compile with the
  matching locally held references/SDK.
- Synthetic registry tests verify targeted apply/restore behavior, preservation
  of unrelated fields and refusal of missing, duplicate or changed target rows.
- Catalog tests exercise navigation across page boundaries and malformed input.
- Shell recipes receive syntax checks; selected SQL blocks are tested against
  synthetic tables.
- Public files receive a review for accidental private/binary artifacts.

These checks do not substitute for visual/controller verification, firmware
compatibility testing or measurement of real input latency on each target.
