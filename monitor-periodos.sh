#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_version="$(sed -n 's/^project(T3DAnalogVelocity VERSION \([0-9.]*\) LANGUAGES.*$/\1/p' "$project_dir/CMakeLists.txt")"
[[ "$project_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
monitor_binary="$project_dir/build/v$project_version/t3d_timing_monitor"
if [[ ! -x "$monitor_binary" ]]; then
    printf '%s\n' 'Monitor ainda não compilado. Abra iniciar.sh antes do teste.' >&2
    exit 1
fi
exec "$monitor_binary" "$@"
