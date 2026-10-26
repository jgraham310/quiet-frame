#!/bin/sh
# Generated plan data is checked by the pinned control manifest before entry.
# First manual trial only. No Home/startup, Art, settings or other app writes.
set -eu
umask 077
test "$(id -u)" = 0
D=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$D/plan-env.sh"
action=${1:?Trial operation required}
label=User::Pkg::com.samsung.tv.adplayer::RO
registry=/opt/dbspace/.pkgmgr_parser.db
app_id=com.samsung.tv.adplayer
expected_row="dotnet-inhouse|$A/bin/AdPlayer.dll|false|false|false"
tab=$(printf '\t')
fail() { printf 'Stopped: %s\n' "$*" >&2; exit 1; }
hash() { sha256sum "$1" | awk '{print $1}'; }
regular() { test -f "$1" && test ! -L "$1" || fail "Expected regular file: $1"; }
check_hash() { regular "$1"; test "$(hash "$1")" = "$2" || fail "File drift: $1"; }
row() { sqlite3 -readonly "$1" "SELECT app_type,app_exec,app_disable,app_onboot,app_autorestart,app_preload FROM package_app_info WHERE app_id='$app_id';"; }
check_registry() {
    value=$(row "$registry")
    case "$value" in "$expected_row|true"|"$expected_row|false") ;;
        *) fail 'AdPlayer registry drift; no fields were overwritten.';; esac
}
check_backup() {
    for directory in "$A" "$A/bin" "$A/bin/.native_image" "$A/res" "$B" "$B/original" "$B/state"; do
        test -d "$directory" && test ! -L "$directory" || fail 'An application or recovery directory changed type.'
    done
    regular "$B/complete"
    check_hash "$B/backup.tar.gz" "$backup_hash"
    test "$(row "$B/state/.pkgmgr_parser.db")" = "$expected_row|true" || fail 'Saved AdPlayer row differs from this trial.'
    while IFS="$tab" read -r digest name relative; do
        check_hash "$B/original/$name" "$digest"
        test "$(stat -c %u:%g "$B/original/$name")" = 201:0 || fail 'Original ownership differs.'
        test "$(ls -dZ "$B/original/$name" | awk '{print $1}')" = "$label" || fail 'Original SMACK label differs.'
    done < "$D/originals.tsv"
}
metadata_matches_original() {
    test "$(stat -c %u:%g:%a "$1")" = "$(stat -c %u:%g:%a "$2")" &&
    test "$(ls -dZ "$1" | awk '{print $1}')" = "$(ls -dZ "$2" | awk '{print $1}')"
}
installed_metadata() {
    test "$(stat -c %u:%g:%a "$1")" = "201:0:$2" || fail "Installed metadata drift: $1"
    test "$(ls -dZ "$1" | awk '{print $1}')" = "$label" || fail "Installed SMACK drift: $1"
}
adplayer_pids() {
    for process in /proc/[0-9]*; do
        test -r "$process/cmdline" || continue
        if arguments=$(tr '\000' '\n' < "$process/cmdline" 2>/dev/null); then :; else continue; fi
        case "$arguments" in *AdPlayer.dll*|*com.samsung.tv.adplayer*) ;; *) continue;; esac
        if printf '%s\n' "$arguments" | grep -F -x -q -e com.samsung.tv.adplayer -e AdPlayer.dll -e "$A/bin/AdPlayer.dll"; then
            if users=$(awk '$1=="Uid:" {print $2 ":" $3 ":" $4 ":" $5}' "$process/status" 2>/dev/null); then
                test "$users" = "$launch_uid:$launch_uid:$launch_uid:$launch_uid" || fail 'AdPlayer runs as an unexpected user.'
                printf '%s\n' "${process##*/}"
            fi
        fi
    done
}
require_stopped() {
    active=$(adplayer_pids) || fail 'Cannot verify AdPlayer process identity.'
    test -z "$active" || fail 'AdPlayer is running; installed files were not replaced.'
}
native_context() {
    context_pid=
    for process in /proc/[0-9]*; do
        test -r "$process/cmdline" || continue
        if arguments=$(tr '\000' '\n' < "$process/cmdline" 2>/dev/null); then :; else continue; fi
        case "$arguments" in *ArtApp.dll*|*csfs.dll*) ;; *) continue;; esac
        if printf '%s\n' "$arguments" | grep -F -x -q -e /usr/apps/org.tizen.art-app/bin/ArtApp.dll -e /usr/apps/com.samsung.tv.csfs/bin/csfs.dll; then
            users=$(awk '$1=="Uid:" {print $2 ":" $3 ":" $4 ":" $5}' "$process/status")
            groups=$(awk '$1=="Gid:" {print $2 ":" $3 ":" $4 ":" $5}' "$process/status")
            test "$users" = "$launch_uid:$launch_uid:$launch_uid:$launch_uid" || fail 'Native UI launch UID changed.'
            test "$groups" = "$launch_gid:$launch_gid:$launch_gid:$launch_gid" || fail 'Native UI launch GID changed.'
            if [ -z "$context_pid" ]; then context_pid=$process; fi
        fi
    done
    test -n "$context_pid" || fail 'No matching native UI process; open Samsung Home and retry.'
    launch_user=$(awk -F: -v uid="$launch_uid" -v gid="$launch_gid" '$3==uid && $4==gid {print $1}' /etc/passwd)
    case "$launch_user" in ''|*[!A-Za-z0-9_-]*) fail 'Cannot resolve a unique native launch account.';; esac
    test -d "/run/user/$launch_uid"
    test "$(stat -c %u "/run/user/$launch_uid")" = "$launch_uid"
    bus=$(tr '\000' '\n' < "$context_pid/environ" | sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p')
    case "$bus" in *'
'*) fail 'Ambiguous native session bus address.';; esac
}
run_helper() {
    native_context
    if [ -n "$bus" ]; then
        /usr/sbin/runuser -u "$launch_user" -- /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin XDG_RUNTIME_DIR="/run/user/$launch_uid" DBUS_SESSION_BUS_ADDRESS="$bus" /usr/bin/dotnet "$D/helper/TrialLaunch.dll" "$@" "$launch_uid" "$launch_gid"
    else
        /usr/sbin/runuser -u "$launch_user" -- /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin XDG_RUNTIME_DIR="/run/user/$launch_uid" /usr/bin/dotnet "$D/helper/TrialLaunch.dll" "$@" "$launch_uid" "$launch_gid"
    fi
}
check_originals_live() {
    check_backup
    test "$(row "$registry")" = "$expected_row|true" || fail 'AdPlayer flags changed since backup.'
    while IFS="$tab" read -r digest name relative; do
        check_hash "$A/$relative" "$digest"
        metadata_matches_original "$A/$relative" "$B/original/$name" || fail "Original metadata drift: $relative"
    done < "$D/originals.tsv"
    test ! -e "$A/res/quiet-home" && test ! -L "$A/res/quiet-home" || fail 'Launcher resources already exist.'
    test ! -e "$A/bin/AdPlayer.deps.json" && test ! -L "$A/bin/AdPlayer.deps.json" || fail 'A deps file already exists.'
    for name in AdPlayer.dll AdPlayer.runtimeconfig.json AdPlayer.deps.json AdPlayer.ni.dll; do
        test ! -e "$A/bin/.quiet-frame-$name.tmp" && test ! -L "$A/bin/.quiet-frame-$name.tmp" || fail 'A trial temporary file already exists.'
    done
    require_stopped
}
check_resources() {
    if [ -e "$A/res/quiet-home" ] || [ -L "$A/res/quiet-home" ]; then
        test -d "$A/res/quiet-home" && test ! -L "$A/res/quiet-home" || fail 'Resources are not a regular directory.'
        find "$A/res/quiet-home" -print | while IFS= read -r path; do
            relative=${path#"$A/"}
            printf '%s\n' "$relative" | grep -F -x -q -f "$D/resource-paths.txt" || fail "Unexpected resource path: $relative"
            test ! -L "$path" || fail 'A resource became a symlink.'
            test -d "$path" || test -f "$path" || fail 'Unexpected resource file type.'
            if [ -d "$path" ]; then installed_metadata "$path" 755; else installed_metadata "$path" 644; fi
        done
    fi
}
check_restorable() {
    check_backup
    check_registry
    while IFS="$tab" read -r digest name relative; do
        if [ -e "$A/$relative" ] || [ -L "$A/$relative" ]; then
            regular "$A/$relative"
            current=$(hash "$A/$relative")
            planned=$(awk -F '\t' -v path="$relative" '$2==path {print $1}' "$D/payload.tsv")
            if [ "$current" = "$digest" ]; then
                metadata_matches_original "$A/$relative" "$B/original/$name" || fail "Original metadata drift: $relative"
            else
                test -n "$planned" && test "$current" = "$planned" || fail "Entry/cache drift: $relative"
                installed_metadata "$A/$relative" 644
            fi
        else
            test "$name" = AdPlayer.ni.dll || fail "Missing entry file: $relative"
        fi
    done < "$D/originals.tsv"
    check_resources
    while IFS="$tab" read -r digest relative; do
        case "$relative" in bin/AdPlayer.dll|bin/AdPlayer.runtimeconfig.json) continue;; esac
        if [ -e "$A/$relative" ] || [ -L "$A/$relative" ]; then
            check_hash "$A/$relative" "$digest"
            installed_metadata "$A/$relative" 644
        fi
    done < "$D/payload.tsv"
}
check_installed() {
    test -f "$D/installed" && test ! -e "$D/restored" || fail 'Trial is not installed.'
    check_restorable
    while IFS="$tab" read -r digest relative; do check_hash "$A/$relative" "$digest"; done < "$D/payload.tsv"
    test ! -e "$A/bin/.native_image/AdPlayer.ni.dll" || fail 'An entry native image reappeared.'
    test "$(row "$registry")" = "$expected_row|false" || fail 'AdPlayer preload flag changed.'
}
atomic_copy() {
    source=$1; target=$2
    temp="$A/bin/.quiet-frame-$(basename "$target").tmp"
    (set -C; : > "$temp") || fail 'Temporary path already exists.'
    cp -a "$source" "$temp"
    mv -T "$temp" "$target"
}
case "$action" in
prepare)
    test ! -e "$D/install-started" || fail 'A trial install was already started.'
    check_originals_live
    test "$(stat -c %d "$D")" = "$(stat -c %d "$A/res")" || fail 'Trial and app must be on the same filesystem.'
    mv --help | grep -q -- --no-target-directory || fail 'The required atomic rename option is unavailable.'
    chmod 755 "$D/helper"
    chmod 644 "$D/helper/TrialLaunch.dll" "$D/helper/TrialLaunch.runtimeconfig.json" "$D/helper/TrialLaunch.deps.json"
    run_helper check
    printf 'prepared\n' > "$D/prepared"
    printf 'Trial prepared; helper identity and app-control creation verified. No installed files or flags changed.\n'
    ;;
install)
    test -s "$D/prepared" || fail 'Prepare the trial first.'
    test ! -e "$D/install-started" || fail 'Install was already started; inspect or restore instead of retrying.'
    check_originals_live
    run_helper check
    # Make the entire resource directory ready off to the side, so interruption
    # never exposes a partly copied asset file at an installed path.
    test ! -e "$D/resources-ready"
    cp -R "$D/payload/res/quiet-home" "$D/resources-ready"
    find "$D/resources-ready" -print | while IFS= read -r path; do
        if [ -d "$path" ]; then mode=755; else mode=644; fi
        chmod "$mode" "$path"
        chown 201:0 "$path"
        chsmack -a "$label" "$path"
        installed_metadata "$path" "$mode"
    done
    require_stopped
    printf 'started\n' > "$D/install-started"
    sqlite3 -bail "$registry" <<SQL
BEGIN IMMEDIATE;
CREATE TEMP TABLE guard(ok INTEGER CHECK(ok=1));
INSERT INTO guard SELECT count(*)=1 FROM package_app_info WHERE app_id='$app_id' AND app_type='dotnet-inhouse' AND app_exec='$A/bin/AdPlayer.dll' AND app_disable='false' AND app_onboot='false' AND app_autorestart='false' AND app_preload='true';
UPDATE package_app_info SET app_preload='false' WHERE app_id='$app_id';
COMMIT;
SQL
    mv -T "$A/bin/.native_image/AdPlayer.ni.dll" "$D/disabled-AdPlayer.ni.dll"
    mv -T "$D/resources-ready" "$A/res/quiet-home"
    for name in AdPlayer.runtimeconfig.json AdPlayer.deps.json AdPlayer.dll; do
        source="$D/payload/bin/$name"
        temp="$A/bin/.quiet-frame-$name.tmp"
        (set -C; : > "$temp") || fail 'Temporary path already exists.'
        cp "$source" "$temp"
        test "$(hash "$temp")" = "$(hash "$source")" || fail 'Temporary file copy failed.'
        chown 201:0 "$temp"
        chmod 644 "$temp"
        chsmack -a "$label" "$temp"
        installed_metadata "$temp" 644
        mv -T "$temp" "$A/bin/$name"
    done
    printf 'installed\n' > "$D/installed"
    check_installed
    printf 'Trial installed. Home/startup, Art and native settings routing were not changed.\n'
    ;;
launch)
    check_installed
    # run_helper appends UID/GID; the helper takes those before the page.
    native_context
    if [ -n "$bus" ]; then
        /usr/sbin/runuser -u "$launch_user" -- /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin XDG_RUNTIME_DIR="/run/user/$launch_uid" DBUS_SESSION_BUS_ADDRESS="$bus" /usr/bin/dotnet "$D/helper/TrialLaunch.dll" launch "$launch_uid" "$launch_gid" home
    else
        /usr/sbin/runuser -u "$launch_user" -- /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin XDG_RUNTIME_DIR="/run/user/$launch_uid" /usr/bin/dotnet "$D/helper/TrialLaunch.dll" launch "$launch_uid" "$launch_gid" home
    fi
    printf 'Launch request submitted; visible UI still needs owner verification.\n'
    ;;
restore)
    test -e "$D/install-started" || fail 'No installation was started.'
    if [ -e "$D/restored" ]; then
        check_backup
        test "$(row "$registry")" = "$expected_row|true" || fail 'State changed after this trial was restored.'
        while IFS="$tab" read -r digest name relative; do
            check_hash "$A/$relative" "$digest"
            metadata_matches_original "$A/$relative" "$B/original/$name" || fail 'Restored metadata changed.'
        done < "$D/originals.tsv"
        test ! -e "$A/bin/AdPlayer.deps.json" && test ! -L "$A/bin/AdPlayer.deps.json" || fail 'A newer trial may own the deps file.'
        test ! -e "$A/res/quiet-home" && test ! -L "$A/res/quiet-home" || fail 'A newer trial may own the resources.'
        printf 'This trial is already restored; original state verified.\n'
        exit 0
    fi
    check_restorable
    pids=$(adplayer_pids)
    if [ -n "$pids" ]; then
        app_launcher -u "$launch_uid" -k "$app_id" || true
        attempts=0
        while :; do
            remaining=$(adplayer_pids) || fail 'Cannot verify trial process identity.'
            test -n "$remaining" || break
            attempts=$((attempts + 1)); test "$attempts" -le 5 || fail 'Trial process did not stop.'
            sleep 1
        done
    fi
    check_restorable
    # Temps are reserved by this plan only. Interrupted copies can have partial
    # bytes, so retain them in the trial directory rather than deleting them.
    for name in AdPlayer.dll AdPlayer.runtimeconfig.json AdPlayer.deps.json AdPlayer.ni.dll; do
        temp="$A/bin/.quiet-frame-$name.tmp"
        if [ -e "$temp" ] || [ -L "$temp" ]; then
            regular "$temp"
            test ! -e "$D/interrupted-$name.tmp" || fail 'Retained interrupted copy already exists.'
            mv -T "$temp" "$D/interrupted-$name.tmp"
        fi
    done
    while IFS="$tab" read -r digest name relative; do
        atomic_copy "$B/original/$name" "$A/$relative"
        metadata_matches_original "$A/$relative" "$B/original/$name" || fail 'Restored metadata differs.'
        check_hash "$A/$relative" "$digest"
    done < "$D/originals.tsv"
    if [ -e "$A/bin/AdPlayer.deps.json" ]; then rm "$A/bin/AdPlayer.deps.json"; fi
    if [ -d "$A/res/quiet-home" ]; then rm -rf "$A/res/quiet-home"; fi
    sqlite3 -bail "$registry" <<SQL
BEGIN IMMEDIATE;
CREATE TEMP TABLE guard(ok INTEGER CHECK(ok=1));
INSERT INTO guard SELECT count(*)=1 FROM package_app_info WHERE app_id='$app_id' AND app_type='dotnet-inhouse' AND app_exec='$A/bin/AdPlayer.dll' AND app_disable='false' AND app_onboot='false' AND app_autorestart='false' AND app_preload IN ('true','false');
UPDATE package_app_info SET app_preload='true' WHERE app_id='$app_id';
COMMIT;
SQL
    printf 'restored\n' > "$D/restored"
    printf 'Original AdPlayer entry/config/cache and metadata restored; new deps/resources removed; preload restored.\n'
    ;;
*) fail 'Unknown trial operation.';;
esac
