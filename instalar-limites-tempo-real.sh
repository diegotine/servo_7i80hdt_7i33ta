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
destination="/usr/local/libexec/t3d-analog-runtime-$runtime_uid"
/usr/bin/install -d -o root -g root -m 0755 /usr/local/libexec
/usr/bin/install -o root -g root -m 0755 "$project_dir/build/t3d_runtime_limiter" "$destination"
if [[ -x /usr/sbin/restorecon ]]; then
    /usr/sbin/restorecon "$destination"
fi
/usr/bin/setcap cap_sys_resource=ep "$destination"
/usr/bin/getcap "$destination"
echo "Instalado para UID $runtime_uid; reabra o aplicativo para usar os limites."
