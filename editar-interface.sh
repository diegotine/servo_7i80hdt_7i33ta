#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
local_designer="$project_dir/.tools/qt-designer/usr/lib64/qt6/bin/designer"
if [[ -x "$local_designer" ]]; then
    export LD_LIBRARY_PATH="$project_dir/.tools/qt-designer/usr/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    exec "$local_designer" "$project_dir/app/mainwindow.ui" "$project_dir/app/axissettingsdialog.ui" "$@"
fi
for designer in designer6 designer-qt6 /usr/lib64/qt6/bin/designer /usr/lib/qt6/bin/designer; do
    if command -v "$designer" >/dev/null 2>&1; then
        exec "$designer" "$project_dir/app/mainwindow.ui" "$project_dir/app/axissettingsdialog.ui" "$@"
    fi
done
printf '%s\n' 'Qt Designer 6 não encontrado. Instale o editor Qt Designer 6 da sua distribuição.' >&2
exit 1
