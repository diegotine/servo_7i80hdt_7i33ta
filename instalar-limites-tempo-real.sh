#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ $(id -u) != 0 ]]; then
    echo 'Execute este instalador via pkexec após compilar o projeto.' >&2
    exit 1
fi
runtime_uid="$(stat -c '%u' "$project_dir")"
if [[ "$runtime_uid" == 0 ]]; then
    echo 'A pasta deve pertencer ao usuário que executa o aplicativo.' >&2
    exit 1
fi
project_version="$(sed -n 's/^project(T3DAnalogVelocity VERSION \([0-9.]*\) LANGUAGES.*$/\1/p' "$project_dir/CMakeLists.txt")"
[[ "$project_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
build_dir="$project_dir/build/v$project_version"
destination="/usr/local/libexec/t3d-analog-runtime-v$project_version-$runtime_uid"
cpu_destination="/usr/local/libexec/t3d-analog-cpu-v$project_version-$runtime_uid"
/usr/bin/install -d -o root -g root -m 0755 /usr/local/libexec
/usr/bin/install -o root -g root -m 0755 "$build_dir/t3d_runtime_limiter" "$destination"
/usr/bin/install -o root -g root -m 0755 "$build_dir/t3d_cpu_policy" "$cpu_destination"
if [[ -x /usr/sbin/restorecon ]]; then
    /usr/sbin/restorecon "$destination"
    /usr/sbin/restorecon "$cpu_destination"
fi
/usr/bin/setcap cap_sys_resource=ep "$destination"
/usr/bin/getcap "$destination"
# Only fixed native helpers run elevated. The runtime helper drops UID and all
# capabilities before Python; the GUI CPU helper never executes user code.
runtime_user="$(getent passwd "$runtime_uid" | cut -d: -f1)"
if [[ ! "$runtime_user" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]]; then
    echo 'Nome de usuário incompatível com a regra restrita.' >&2
    exit 1
fi
rule_temp="$(mktemp)"
trap 'rm -f "$rule_temp"' EXIT
printf '%s ALL=(root) NOPASSWD: %s\n' "$runtime_user" "$destination" > "$rule_temp"
printf '%s ALL=(root) NOPASSWD: %s\n' "$runtime_user" "$cpu_destination" >> "$rule_temp"
/usr/bin/visudo -cf "$rule_temp"
rule_version="${project_version//./_}"
/usr/bin/install -o root -g root -m 0440 "$rule_temp" "/etc/sudoers.d/t3d-analog-v$rule_version-$runtime_uid"
echo "Instalado para UID $runtime_uid; reabra o aplicativo para usar os limites."
