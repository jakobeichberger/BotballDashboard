#!/bin/sh
# Hands the writable directories to the unprivileged app user (uid 10001).
#
# Runs in the one-shot compose services "volume-permissions" (uploads, VAPID
# key) and "backup-permissions" (backup archives, off-site credentials) before
# the application containers start. Those run as root, but with every
# capability dropped except CHOWN (change owners) and DAC_READ_SEARCH (walk
# directories), without network and without new privileges.
#
# Needed once after the update from a release whose containers ran as root
# (its files are root-owned), and whenever root creates files there again,
# e.g. a host directory made by scripts/proxmox-setup.sh. Only entries not yet
# owned by the app user are touched, so every later start is cheap. Symbolic
# links are changed themselves (-h), never followed.
#
#   fix-volume-ownership.sh UID:GID DIR...
set -eu

owner="$1"
shift
uid="${owner%%:*}"
gid="${owner##*:}"
for dir in "$@"; do
  [ -d "$dir" ] || continue
  count="$(find "$dir" -xdev \( ! -user "$uid" -o ! -group "$gid" \) -print | wc -l)"
  if [ "$count" -gt 0 ]; then
    find "$dir" -xdev \( ! -user "$uid" -o ! -group "$gid" \) -exec chown -h "$owner" {} +
    echo "fix-volume-ownership: ${dir}: ${count} entries now owned by ${owner}"
  fi
done
