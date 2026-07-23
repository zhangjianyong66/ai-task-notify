#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'setup.sh: 未找到 python3（需要 Python 3.10+）' >&2
  exit 127
fi
exec python3 "$SCRIPT_DIR/setup_config.py" "$@"
