#!/usr/bin/env bash
# Deployed negative control for the shuttle signing broker (aegis-za4f.19.2).
# Run AS braino (the job uid) on the host. Every probe must be REFUSED; any
# probe that succeeds exits 1 and names itself. Exit 0 = key material is
# unreachable from this uid.
set -uo pipefail
pid=$(systemctl show -p MainPID --value shuttle-signer)
[ -n "$pid" ] && [ "$pid" != 0 ] || { echo "UNKNOWN: shuttle-signer not running"; exit 2; }
owner=$(stat -c %U "/proc/$pid" 2>/dev/null || echo '?')
[ "$owner" = shuttle-signer ] || { echo "FAIL: broker runs as '$owner', not shuttle-signer"; exit 1; }
[ "$(id -u)" != "$(id -u shuttle-signer)" ] || { echo "UNKNOWN: run me as the job uid"; exit 2; }
fail=0
probe() { if "$@" >/dev/null 2>&1; then echo "FAIL: readable: $*"; fail=1; else echo "refused: $*"; fi; }
probe head -c1 "/proc/$pid/mem"
probe head -c1 "/proc/$pid/environ"
probe ls "/proc/$pid/fd"
probe gdb -batch -p "$pid" -ex 'info proc'
files=$(find / -xdev -user shuttle-signer -type f -readable 2>/dev/null | head -5)
if [ -n "$files" ]; then echo "FAIL: shuttle-signer files readable: $files"; fail=1; else echo "refused: no readable shuttle-signer files"; fi
[ "$fail" = 0 ] && echo "PASS: no key material reachable as $(id -un)"
exit "$fail"
