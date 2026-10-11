#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_version="$(sed -n 's/^project(T3DAnalogVelocity VERSION \([0-9.]*\) LANGUAGES.*$/\1/p' "$project_dir/CMakeLists.txt")"
[[ "$project_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
build_dir="$project_dir/build/v$project_version"
cmake -S "$project_dir" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --parallel 4
exec "$build_dir/t3d_analog" "$@"
