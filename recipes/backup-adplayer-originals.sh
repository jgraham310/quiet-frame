#!/bin/sh
# Fixed preparation only: preserve originals and SQLite snapshots; never install.
set -eu
umask 077
test "$(id -u)" = 0
test "$#" = 6
name=$1; stage=$2; sdk_uid=$3; dll_hash=$4; config_hash=$5; mode=$6
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
case "$sdk_uid" in ''|*[!0-9]*) exit 1;; esac
case "$stage" in /home/owner/share/tmp/sdk_tools/archive-root-*) ;; *) exit 1;; esac
test -d "$stage"
backup_dir=/opt/usr/share/quiet-frame-backups/$name
source_dir=/opt/usr/apps/com.samsung.tv.adplayer
if [ "$mode" = create ]; then
    test ! -e "$backup_dir" || { echo "Backup already exists; use --fetch-existing for a completed copy." >&2; exit 1; }
    test ! -e "$source_dir/res/quiet-home"
    test ! -e "$source_dir/bin/AdPlayer.deps.json"
    printf '%s  %s\n' "$dll_hash" "$source_dir/bin/AdPlayer.dll" "$config_hash" "$source_dir/bin/AdPlayer.runtimeconfig.json" | sha256sum -c -
    for file in "$source_dir/bin/AdPlayer.dll" "$source_dir/bin/AdPlayer.runtimeconfig.json" "$source_dir/bin/.native_image/AdPlayer.ni.dll"; do
        test -f "$file"
        test ! -L "$file"
        test "$(stat -c %u:%g "$file")" = 201:0
    done
    test "$(sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db "SELECT count(*) FROM package_app_info WHERE app_id='com.samsung.tv.adplayer' AND app_type='dotnet-inhouse' AND app_exec='/opt/usr/apps/com.samsung.tv.adplayer/bin/AdPlayer.dll' AND app_disable='false' AND app_onboot='false' AND app_autorestart='false' AND app_preload='true';")" = 1
    mkdir -p "$backup_dir/original" "$backup_dir/state"
    printf 'Backup directory: %s\n' "$backup_dir"
    sha256sum "$source_dir/bin/AdPlayer.dll" "$source_dir/bin/AdPlayer.runtimeconfig.json" "$source_dir/bin/.native_image/AdPlayer.ni.dll" > "$backup_dir/state/live-files-before.sha256"
    cp -a "$source_dir/bin/AdPlayer.dll" "$backup_dir/original/"
    cp -a "$source_dir/bin/AdPlayer.runtimeconfig.json" "$backup_dir/original/"
    cp -a "$source_dir/bin/.native_image/AdPlayer.ni.dll" "$backup_dir/original/"
    for file in "$source_dir/bin/AdPlayer.dll" "$source_dir/bin/AdPlayer.runtimeconfig.json" "$source_dir/bin/.native_image/AdPlayer.ni.dll"; do
        copied="$backup_dir/original/$(basename "$file")"
        test "$(stat -c %u:%g:%a "$file")" = "$(stat -c %u:%g:%a "$copied")"
        test "$(ls -dZ "$file" | awk '{print $1}')" = "$(ls -dZ "$copied" | awk '{print $1}')"
    done
    cp -a "$source_dir/tizen-manifest.xml" "$backup_dir/state/"
    for database in .pkgmgr_parser .app-context; do
        sqlite3 -readonly "/opt/dbspace/$database.db" ".backup '$backup_dir/state/$database.db'"
        test "$(sqlite3 -readonly "$backup_dir/state/$database.db" 'PRAGMA quick_check;')" = ok
    done
    sqlite3 -readonly -header -csv /opt/dbspace/.pkgmgr_parser.db "SELECT app_id,app_type,app_exec,app_disable,app_onboot,app_autorestart,app_preload FROM package_app_info ORDER BY app_id;" > "$backup_dir/state/apps-before.csv"
    stat -c 'owner=%u group=%g mode=%a bytes=%s path=%n' "$source_dir/bin/AdPlayer.dll" "$source_dir/bin/AdPlayer.runtimeconfig.json" "$source_dir/bin/.native_image/AdPlayer.ni.dll" > "$backup_dir/state/file-metadata.txt"
    ls -ldZ "$source_dir/bin/AdPlayer.dll" "$source_dir/bin/AdPlayer.runtimeconfig.json" "$source_dir/bin/.native_image/AdPlayer.ni.dll" >> "$backup_dir/state/file-metadata.txt"
    vconftool get db/appfw/home_appid > "$backup_dir/state/home-preference.txt"
    if startup=$(vconftool get db/appfw/startup_appid 2>&1); then
        printf '%s\n' "$startup" > "$backup_dir/state/startup-preference.txt"
    else
        case "$startup" in
            *"Key 'db/appfw/startup_appid': No such file or directory"*) printf 'absent (not created)\n' > "$backup_dir/state/startup-preference.txt";;
            *) printf '%s\n' "$startup" >&2; exit 1;;
        esac
    fi
    printf 'SDK session UID (not a guessed launch UID): %s\n' "$sdk_uid" > "$backup_dir/state/user-evidence.txt"
    for user_dir in /run/user/[0-9]*; do
        if [ -d "$user_dir" ]; then stat -c 'runtime directory owner=%u path=%n' "$user_dir" >> "$backup_dir/state/user-evidence.txt"; fi
    done
    app_launcher --help-all > "$backup_dir/state/launch-help.txt" 2>&1 || true
elif [ "$mode" = resume ]; then
    test -d "$backup_dir/original"
    test ! -e "$backup_dir/complete"
    test ! -e "$backup_dir/backup.tar.gz"
    test ! -e "$backup_dir/export.tmp.tar.gz"
    test ! -e "$backup_dir/state/original-files.sha256"
    test ! -e "$backup_dir/state/restore-plan.txt"
    for file in live-files-before.sha256 tizen-manifest.xml apps-before.csv file-metadata.txt home-preference.txt startup-preference.txt user-evidence.txt launch-help.txt; do
        test -s "$backup_dir/state/$file"
    done
    for database in .pkgmgr_parser .app-context; do
        test -s "$backup_dir/state/$database.db"
        test "$(sqlite3 -readonly "$backup_dir/state/$database.db" 'PRAGMA quick_check;')" = ok
    done
    printf '%s  %s\n' "$dll_hash" "$source_dir/bin/AdPlayer.dll" "$config_hash" "$source_dir/bin/AdPlayer.runtimeconfig.json" | sha256sum -c -
    printf 'Resuming finalization; existing originals and snapshots are retained: %s\n' "$backup_dir"
elif [ "$mode" != fetch ]; then
    exit 1
fi
if [ "$mode" != fetch ]; then
    sha256sum -c "$backup_dir/state/live-files-before.sha256"
    for file in "$source_dir/bin/AdPlayer.dll" "$source_dir/bin/AdPlayer.runtimeconfig.json" "$source_dir/bin/.native_image/AdPlayer.ni.dll"; do
        copied="$backup_dir/original/$(basename "$file")"
        test -f "$copied"
        test ! -L "$copied"
        source_sum=$(sha256sum "$file")
        copied_sum=$(sha256sum "$copied")
        test "${source_sum%% *}" = "${copied_sum%% *}"
        test "$(stat -c %u:%g:%a "$file")" = "$(stat -c %u:%g:%a "$copied")"
        test "$(ls -dZ "$file" | awk '{print $1}')" = "$(ls -dZ "$copied" | awk '{print $1}')"
    done
    (cd "$backup_dir/original" && sha256sum AdPlayer.dll AdPlayer.runtimeconfig.json AdPlayer.ni.dll) > "$backup_dir/state/original-files.sha256"
    cat > "$backup_dir/state/restore-plan.txt" <<'PLAN'
Manual trial scope: entry DLL, runtime configuration, new deps/resources, entry AOT cache and AdPlayer preload only. No Home/startup or Art/settings routing changes.
Before installation, record hashes for every installed file and whether each added path was originally absent. Record the selected launch UID from actual device evidence.
Rollback must reject drift in installed hashes and registry fields, then stop only the trial AdPlayer process using the recorded UID.
Restore original/AdPlayer.dll and original/AdPlayer.runtimeconfig.json to matching bin paths. Restore original/AdPlayer.ni.dll to bin/.native_image/AdPlayer.ni.dll. Preserve recorded owner/group/mode and SMACK labels from file-metadata.txt.
Remove only trial-created AdPlayer.deps.json and res/quiet-home after verifying installed hashes. Restore only the AdPlayer preload field if the trial changed it; never replace a live registry with this snapshot.
A tested executable inverse and a verified local backup are required before installation. This backup operation performs none of the trial changes.
PLAN
    tar -czf "$backup_dir/export.tmp.tar.gz" -C "$backup_dir" original state
    test "$(stat -c %s "$backup_dir/export.tmp.tar.gz")" -le 4194304
    mv "$backup_dir/export.tmp.tar.gz" "$backup_dir/backup.tar.gz"
    sha256sum "$backup_dir/backup.tar.gz" > "$backup_dir/backup.sha256"
    printf 'complete\n' > "$backup_dir/complete"
fi
test -s "$backup_dir/complete"
sha256sum -c "$backup_dir/backup.sha256"
cp "$backup_dir/backup.tar.gz" "$stage/adplayer-backup.tar.gz"
printf '\n=== SDK/user evidence ===\n'
cat "$backup_dir/state/user-evidence.txt"
printf '\n=== Launch utility options ===\n'
cat "$backup_dir/state/launch-help.txt"
printf '\nOriginal application files and Home routing were not changed.\n'
