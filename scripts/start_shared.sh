#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
expected_repo='C:\Users\utilisateur\Desktop\Materiel-stage3-maintenance-operations'
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

if [[ -z "$(git status --porcelain)" ]]; then
  git fetch --no-write-fetch-head origin \
    refs/heads/stage3-maintenance-operations:refs/remotes/origin/stage3-maintenance-operations
  git merge --ff-only origin/stage3-maintenance-operations
else
  printf 'Serving the current local working tree; local edits were preserved and not synchronized.\n'
fi

shared_db='C:/Users/utilisateur/Desktop/Materiel/fleet_assets.local-20261017.db'
if [[ ! -f "$shared_db" ]]; then
  printf 'Shared database not found: %s\n' "$shared_db" >&2
  exit 1
fi

export DATABASE_URL="sqlite:///$shared_db"
export APP_HOST="${APP_HOST:-127.0.0.1}"
export APP_PORT="${APP_PORT:-8000}"

python run_web.py
