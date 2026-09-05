#!/usr/bin/env bash
set -euo pipefail

health_check() {
  python - <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception:
    sys.exit(1)
PY
}

if health_check; then
  exit 0
fi

nohup python run_web.py > /tmp/materiel-web.log 2>&1 &

for _ in $(seq 1 30); do
  if health_check; then
    exit 0
  fi
  sleep 1
done

cat /tmp/materiel-web.log
exit 1
