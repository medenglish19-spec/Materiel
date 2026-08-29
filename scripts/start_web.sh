#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
else
    PYTHON="$(command -v python3 || command -v python)"
fi

if "$PYTHON" -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)' >/dev/null 2>&1; then
    exit 0
fi

nohup "$PYTHON" "$ROOT/run_web.py" > /tmp/materiel-web.log 2>&1 &
echo $! > /tmp/materiel-web.pid
sleep 1

if ! "$PYTHON" -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)' >/dev/null 2>&1; then
    echo "Materiel web server failed to start. Log: /tmp/materiel-web.log" >&2
    cat /tmp/materiel-web.log >&2 || true
    exit 1
fi

echo "Materiel Web: http://127.0.0.1:8000"
