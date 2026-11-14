#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
expected_repo='D:\Materiel-stage3-maintenance-operations'
actual_repo="$(cygpath -aw "$repo_root")"
actual_repo="${actual_repo,,}"
expected_repo="${expected_repo,,}"

if [[ "$actual_repo" != "$expected_repo" ]]; then
  printf 'Start the shared server from %s (current checkout: %s).\n' "$expected_repo" "$actual_repo" >&2
  exit 1
fi

cd "$repo_root"
branch="$(git branch --show-current)"
if [[ "$branch" != 'stage3-maintenance-operations' ]]; then
  printf 'Refusing to start on branch %s; expected stage3-maintenance-operations.\n' "$branch" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  printf 'Refusing to start with uncommitted changes in %s. Commit the intended changes, then rerun this script.\n' "$repo_root" >&2
  exit 1
fi

git fetch --no-write-fetch-head origin \
  refs/heads/stage3-maintenance-operations:refs/remotes/origin/stage3-maintenance-operations
git merge --ff-only origin/stage3-maintenance-operations

shared_db='D:/Materiel/fleet_assets.db'
backup_dir='D:/Materiel-database-backups'
python_bin='D:/Materiel/.venv/Scripts/python.exe'
if [[ ! -x "$python_bin" ]]; then
  printf 'Shared Python environment not found: %s\n' "$python_bin" >&2
  exit 1
fi
if [[ ! -f "$shared_db" ]]; then
  printf 'Shared database not found: %s\n' "$shared_db" >&2
  exit 1
fi

export DATABASE_URL="sqlite:///$shared_db"
export MATERIEL_DB_BACKUP_DIR="$backup_dir"
export APP_HOST="${APP_HOST:-127.0.0.1}"
export APP_PORT="${APP_PORT:-8000}"

"$python_bin" scripts/backup_shared_database.py "$shared_db" --backup-dir "$backup_dir"
"$python_bin" scripts/check_db_health.py "$shared_db"
"$python_bin" run_web.py
