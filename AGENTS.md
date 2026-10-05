# Materiel — AGENTS.md

> This file merges the project-wide operating rules with **verified facts about this
> repository as it stands today**. Sections marked *(verified)* were checked against the
> code, not copied from prose — where `README.md` / `PROJECT_MAP.md` /
> `docs/MATERIEL_EXECUTION_MAP.md` disagree with the code, the code wins.

---

## Project

Materiel is an Arabic-first fleet/equipment management system.

Main stack:

* Python
* FastAPI
* SQLAlchemy
* SQLite
* Alembic
* HTML/CSS/JavaScript
* pytest
* Git/GitHub

The application is designed for real operational equipment/fleet management, maintenance, spare parts, missions, meters, tires, batteries, master data, and related workflows.

The interface is primarily Arabic and RTL.

---

## Core Engineering Rules

### 1. Inspect before modifying

Before changing code:

* inspect the relevant existing implementation;
* identify the route, service, model, template, JavaScript, migration, and tests involved;
* understand the existing data flow;
* do not replace working architecture with a speculative implementation;
* prefer the smallest correct change.

Do not create duplicate implementations when an existing service, route, component, or model already provides the required behavior.

### 2. Preserve existing architecture

Do not introduce unnecessary architectural changes.

Prefer the existing project patterns for:

* FastAPI routes
* services
* SQLAlchemy models
* templates
* JavaScript
* migrations
* validation
* tests

Do not introduce a new framework or dependency unless it is clearly necessary.

### 3. Database safety

The database is operational project data.

Never perform destructive database operations casually.

Before schema migrations or risky database changes:

1. inspect the current schema;
2. inspect Alembic history;
3. create a backup of the relevant SQLite database when appropriate;
4. create a proper Alembic migration;
5. verify upgrade behavior;
6. verify application startup afterward.

Never silently delete production-like data to make tests pass.

Do not modify historical migrations merely to repair a current problem unless there is a compelling repository-level reason.

---

## Git Rules

The working branch is normally:

`stage3-maintenance-operations`

Always inspect:

```bash
git status -sb
git branch -vv
git log --oneline --decorate -10
```

before significant Git operations.

Keep local and GitHub history synchronized.

Do not:

* force-push;
* reset hard;
* rebase shared history;
* delete branches;
* overwrite another person's commits;

unless explicitly instructed.

### Commit policy

Do not create a commit merely because a modification works.

Create a commit only when the user explicitly requests:

* commit
* commit + push
* push
* تنفيذ commit
* نفذ commit
* commit and push

When explicitly requested, make a focused commit with a clear message.

Do not mix unrelated fixes into one commit.

### Push policy

Never push automatically unless the user explicitly requests a push.

Before pushing:

```bash
git status -sb
git log --oneline --decorate -5
```

Confirm the intended branch and commit.

---

## Testing Rules

After code changes, run the smallest relevant tests first.

Then run the broader test suite when practical.

Typical command:

```bash
python -m pytest -q
```

If pytest is unavailable, do not silently install dependencies without checking the project environment and requirements first.

When tests fail:

* distinguish collection/import/syntax errors from assertion failures;
* inspect the actual failure;
* fix the underlying problem;
* do not weaken or delete tests simply to obtain a green result.

A failing test is information about the implementation, not an obstacle to hide.

---

## Application Startup

The official startup path is the one the repository already provides — `run_web.py`,
whose docstring calls it the project's single entry point:

```bash
python run_web.py
# → http://localhost:8000
```

It reads `APP_HOST` / `APP_PORT` / `DATABASE_URL` from `app/core/config.py`.
The raw uvicorn form also works but **bypasses `settings.HOST` / `settings.PORT`**:

```bash
python -m uvicorn web.main:app --host 127.0.0.1 --port 8000
```

Prefer `python run_web.py`. Do not invent a different startup path if the existing project already provides one.

When modifying startup behavior, also inspect:

* `web/main.py`
* application initialization
* database initialization
* migrations
* `run_web.py` if present
* startup-related tests

The official startup path must remain functional.

---

# Domain Rules

## Equipment

Equipment status must distinguish between:

* operational/equipment state;
* maintenance/repair state;
* meter state.

Do not interpret a stopped/non-working meter as proof that the equipment itself is broken.

Effective equipment status may be affected by active repairs, but meter readings/history must remain logically separate from equipment operational state.

Do not let meter readings overwrite equipment operational status.

## Dashboard

Dashboard indicators must represent meaningful operational concepts.

Current intended dashboard concepts include:

* technical readiness percentage;
* broken equipment count;
* equipment currently in repair;
* internal workshop repair;
* external workshop repair;
* equipment in mission;
* pending spare-parts requests.

Do not reintroduce ambiguous cards such as "available" or generic "readiness" when the intended metric is technical readiness.

When changing dashboard calculations, verify the underlying equipment and repair data rather than only changing displayed numbers.

---

# Maintenance Architecture

Maintenance consists of three conceptual layers:

1. General maintenance operation library.
2. Maintenance plans linked to equipment models.
3. Maintenance execution and `MaintenanceRecord` history.

The general operation library contains reusable maintenance operations.

Do not treat the operation library as a technical-properties library.

Maintenance plan conditions and operation conditions are separate concepts.

Do not mix:

* plan conditions;
* operation conditions;
* technical properties.

Supported maintenance axes include:

* kilometers;
* operating hours;
* time/date based conditions where already supported.

Maintenance operations may be grouped by systems such as:

* engine;
* electrical system;
* brakes;
* cooling;
* transmission;
* steering;
* suspension;
* tires;
* other relevant equipment systems.

Maintenance execution should respect the configured operation/condition rules and must preserve historical records.

Avoid reintroducing obsolete compatibility layers such as the old `MaintenanceRule` architecture when the current codebase has already migrated away from it.

---

# Spare Parts

Spare-parts workflows must preserve traceability.

The system must prevent:

* distributing more quantity than was received;
* returning more quantity than remains returnable;
* losing received spare parts without traceability;
* silently changing quantities in a way that bypasses inventory history.

Received quantities, distributed quantities, returned quantities, and remaining quantities must remain logically consistent.

A spare-parts request number must not be duplicated.

When editing requests, prefer direct edit behavior appropriate to the existing UI rather than introducing unnecessary separate editing interfaces.

Do not change inventory quantities without updating the corresponding movement/history logic when the architecture requires it.

---

# Master Data

Master data is centralized.

Equipment models use centrally defined technical property definitions/values rather than duplicating technical definitions for every model.

Relevant concepts include:

* equipment category;
* equipment type;
* brand;
* model;
* technical property definitions;
* technical property values.

Preserve the distinction between:

* master definitions;
* model-specific selected values;
* individual equipment data.

Do not duplicate master-data definitions unnecessarily.

The master-data interface is RTL and must remain usable on desktop and mobile.

---

# UI / UX

The application is Arabic-first and RTL.

When modifying UI:

* preserve RTL direction;
* keep related fields visually close;
* avoid excessive horizontal spacing;
* maintain usable mobile layouts;
* do not hide important actions behind unnecessary icons;
* use clear Arabic labels that match the actual function;
* preserve existing visual language unless the task explicitly requests a redesign.

For mobile interfaces, test that buttons remain reachable and that forms do not create excessive horizontal scrolling.

Do not solve a layout problem by arbitrarily shrinking all fields.

---

# File Organization

Before adding a new file, check whether an existing file already handles the same responsibility.

Prefer:

* route logic in the appropriate route/module;
* business logic in services;
* database structure in models/migrations;
* presentation in templates;
* client-side interaction in the appropriate JavaScript files;
* tests in `tests/`.

Do not put business logic into templates merely for convenience.

Do not duplicate service logic in multiple routes.

---

# API / Validation

Validate input at the appropriate boundary.

Server-side validation is authoritative.

Client-side validation may improve UX but must not replace server-side validation.

Return clear errors consistent with the existing project's conventions.

Do not bypass authorization checks to make a feature work.

---

# Security

Never:

* hard-code credentials;
* commit secrets;
* expose database credentials;
* disable authorization merely to pass a test;
* weaken authentication/authorization checks without explicit instruction.

If authentication or authorization is involved, preserve the existing security model.

---

# Debugging Method

When fixing a bug:

1. reproduce or identify the exact failure;
2. locate the responsible code path;
3. inspect related models/services/templates/tests;
4. make the smallest correct fix;
5. run targeted tests;
6. run broader tests when appropriate;
7. inspect `git diff`;
8. report what changed and what remains failing.

Do not hide errors with broad exception handlers.

Do not catch `Exception` merely to prevent an application error from appearing.

---

# Migration Method

For schema changes:

1. inspect current models;
2. inspect current database schema;
3. inspect Alembic history;
4. back up the SQLite database when appropriate;
5. create a new migration;
6. apply it;
7. verify the resulting schema;
8. run relevant tests;
9. verify application startup.

Do not manually edit the database as a substitute for a migration unless explicitly required for recovery/debugging.

---

# OpenCode Working Rules

OpenCode must work conservatively.

Before modifying multiple files, understand their relationships.

When a task says "نفّذ":

* implement the requested change;
* inspect the diff;
* run relevant tests;
* report the exact files changed.

When a task says "commit":

* create a focused commit.

When a task says "push":

* push only after confirming the current branch and intended commit.

When the user says "commit + push":

* perform both operations.

Do not interpret ordinary requests to inspect, fix, test, or modify code as permission to push.

---

# Completion Checklist

Before declaring a task complete:

* [ ] Correct files were identified.
* [ ] Existing architecture was preserved.
* [ ] No unnecessary duplicate implementation was added.
* [ ] Validation/security behavior was preserved.
* [ ] Relevant tests were run.
* [ ] Failures were investigated rather than hidden.
* [ ] Database changes use the appropriate migration process.
* [ ] `git diff` was reviewed.
* [ ] Git status was checked.
* [ ] No commit was created unless requested.
* [ ] No push was performed unless requested.

The goal is a stable, maintainable, operational Materiel system — not merely code that passes one test or produces the expected screen.

---

# Repository Facts *(verified — these override the docs)*

Everything below was read from the code or measured, not taken from prose.

## Commands *(verified)*

```powershell
# setup
python -m venv .venv; .venv\Scripts\activate; pip install -r requirements.txt

python run_web.py                                     # official entrypoint, :8000, admin / Admin@123

.venv\Scripts\python -m pytest -q                     # full suite: 632 passed, 1 skipped (~95s)
.venv\Scripts\python -m pytest tests/test_labels.py -q # one file
.venv\Scripts\python -m pytest -q -k "effective_operational"   # one topic
python -m compileall -q app web run_web.py             # CI's syntax gate
python scripts/check_db_health.py [some_copy.db]       # read-only, exit 1 = real problem
python scripts/seed_operational_demo.py [--remove]     # demo data — WRITES to DATABASE_URL
```

There is **no `conftest.py`**; `pytest.ini` supplies `pythonpath = .`, so **run pytest from the
repository root**. Without the venv activated, use the explicit `.venv\Scripts\python` form.

## Database traps that cost data *(verified)*

1. **Never boot a dev server against `fleet_assets.db`.** `init_db()` runs at startup and it
   *rewrites data*, not just schema. Copy first:
   `Copy-Item fleet_assets.db fleet_assets.dev.db; $env:DATABASE_URL="sqlite:///./fleet_assets.dev.db"`.
   `.devcontainer/start_materiel.sh` starts the app with **no** `DATABASE_URL` — i.e. on the live file.
2. **Startup mutates rows** (`app/database/init_db.py`). `cleanup_legacy_readings` **deletes**
   meter readings that are future-dated, negative, or decreasing per equipment; the startup then
   rewrites `current_odometer` / `current_hours` and drops unused built-in categories. Backup
   before starting the app on data you cannot lose.
3. **`alembic upgrade head` cannot build an empty database.** The chain starts from a `0006`
   baseline that assumes the tables already exist; it dies with `no such table: equipment_models`
   (reproduced locally). A fresh database goes through `create_all` + `stamp head`:
   `DATABASE_URL=sqlite:///./fresh.db` then
   `python -c "from app.database.init_db import init_db; init_db()"`.
   Use `alembic upgrade head` only to move an **already stamped** database forward.
4. **`alembic.ini` carries no `sqlalchemy.url` on purpose.** `migrations/env.py` resolves
   caller-passed URL → else `settings.DATABASE_URL`. Adding a URL to the ini silently overrides it.
5. FKs are enforced by a **per-connection** `PRAGMA foreign_keys=ON` in `app/database/session.py`
   (the engine is built once, connections come and go). Do not move it to engine creation — 704
   orphan rows accumulated once. `scripts/check_db_health.py` reports orphans, a stamp that is not
   head, and stray `_alembic_tmp_` tables (a half-applied `batch_alter_table` makes the *next*
   migration fail with "table already exists").
6. Migration order follows `down_revision`, not filename — the files mix `000N_*` and `stageN_*`.
   SQLite runs with `render_as_batch=True`, and batch migrations must **name** their foreign-key
   constraints (`tests/test_schema_foreign_keys.py`).
7. New model packages must be imported in `app/database/model_registry.py` (which also calls
   `configure_mappers()`), or `create_all`/migrations miss them and the first query fails.

## Wiring *(verified)*

- `run_web.py` → `web.main:app`. **`web/main.py::create_app()` registers every router by hand** —
  a module that is not `include_router`ed there simply 404s.
- `app/modules/<name>/` = `models.py` · `schemas.py` · `services.py` · `router.py` · `templates/`.
- Second files are real and easy to misread as dead code: `faults_repairs/routes.py` and
  `spare_parts_movements/routes.py` are *pages* routers; `spare_parts_requests/routes.py` holds
  page functions; `meter_readings/audit_router.py` is a second router.
- `app/modules/asset_movements/` has **no router on purpose** — shared policy enforcing
  "Move = Remove + Install" and "never overwrite an install record to hide history".
- Guard rail: **Source Data → Domain Service → Aggregation → Page.** The dashboard is never a
  source of truth, and a notification must not redefine its domain's rule.
- `app/core/labels.py` is the **only** place an enum key becomes Arabic. `label()` /
  `label_options()` / `LABELS` are injected by the single Jinja factory
  `app/core/templating.py::get_module_templates()`. `tests/test_labels.py` fails on inline label
  dicts or `if/elif` label chains in templates. JS reads `{{ LABELS | tojson }}`.
- Logging is queue-backed (`app/core/logging.py`): use `get_logger(...)`, **never `print()`** in
  `app/` — `tests/test_logging.py` scans the source for it.

## Tests *(verified)*

- **A green run does not mean the whole suite ran.** The single skip is `tests/edit_manager/` —
  that package does `pytest.importorskip("playwright.sync_api")` and playwright is **not** in
  `requirements.txt`, so it is skipped locally *and in CI*. If you touch the edit manager,
  install playwright plus its browsers and run that file explicitly, or you are shipping
  unverified. Use `-rs` to read skip reasons instead of trusting the exit code.
- Many `*_contract.py` / `*_ui_contract.py` / `*_integrity.py` files assert **exact markup, IDs
  and JS function names**. Editing a template or a `static/js/master-data-tree.js` attribute
  (`data-tree-edit`, `data-equipment-type-id`, `data-category-id`, `.tree-group`) breaks them by
  design — read the asserting test before changing the markup.
- Every template under `app/**/templates/` must `{% extends "base.html" %}` and must not carry its
  own `<!doctype>`, `<html>` or `<body>` (`users/templates/login.html` excepted). The RTL shell
  lives in `web/templates/base.html` + `static/css/style.css`.
- Page rendering is only covered by `tests/test_authenticated_pages.py`; a plain `pytest` run will
  not notice a route that renders nothing. Use it after touching routers or context variables.
- Tests must never read `fleet_assets.db`. **Both** overrides are needed:
  `dependency_overrides[get_db]` for routers **and** a patched `SessionLocal` for modules that
  open their own session inside a function (`meter_readings/audit.py`).
- Seed test data through the real services (e.g. `missions.services.add_mission`), not raw
  INSERTs — only the service path sets a state the application can actually produce.
- `tests/test_run_web_smoke.py` grabs a free ephemeral port, so it does **not** require port 8000
  to be free.

## Framework quirks that already bit this repo *(verified)*

- **FastAPI ≥ 0.142 / Starlette 1.7** — the positional `TemplateResponse(name, context)` form was
  removed. Always `TemplateResponse(request=request, name=..., context=...)`.
- `include_router` results are `_IncludedRouter` wrappers with no `.path`. Enumerating routes means
  walking `route.original_router.routes` — see `_route_count()` in `web/main.py` and
  `_registered_paths()` in `tests/test_navigation_and_routes.py`.
- **SQLAlchemy 2.1** rejects an empty list inside `filter(...)`; guard the filter instead.
- **`bcrypt` is pinned to `4.0.1`** because `passlib 1.7.4` breaks on bcrypt ≥ 4.1. Do not close
  that version lag without replacing passlib.
- CI rejects any tracked filename that is all digits or contains a space, `"` or `'`.
- Auth is a JWT cookie (`fleet_session`). Authorization belongs in the backend; hiding a button is
  not protection. Roles: `ADMIN`, `FLEET_MANAGER`, `OPERATOR`, `VIEWER`.

## Startup security warnings *(verified — they log, they never block)*

`app/core/config.py::security_warnings()` logs at startup that `SECRET_KEY` is still the published
default and that `admin` is still on `Admin@123`. It never refuses to boot and never rewrites the
password. Set a 32+ character `SECRET_KEY` in **any** shared environment, not only production.

Env vars: `DATABASE_URL` · `SECRET_KEY` · `APP_HOST` · `APP_PORT` · `APP_ENV` ·
`UVICORN_RELOAD` · `ACCESS_TOKEN_EXPIRE_MINUTES` · `LOG_LEVEL` · `LOG_DIR`.
`UVICORN_RELOAD` defaults to **false** — leave it off; reload made `init_db`/Alembic run twice.

## Where the docs are stale *(verified — trust the code)*

- `README.md` and `PROJECT_MAP.md` cite **52 migrations** and **319/320 tests**. The tree actually
  has **66 revisions** and a verified **632 passed / 1 skipped**.
- Neither doc lists the `spare_parts_requests` / `spare_parts_movements` modules.
- Both docs claim `tests/test_run_web_smoke.py` needs port 8000 free. It does not.
- `docs/MATERIEL_EXECUTION_MAP.md` still describes a "Maintenance **Rule** linked to the Model".
  That model is **gone** — `app/modules/maintenance/models.py` defines `MaintenanceOperationGroup`,
  `MaintenanceOperation`, `MaintenancePlan`, `MaintenancePlanOperation`, `MaintenanceRecord`.
  Use the operation-library + plan + record architecture documented above.
- `tests/test_edit_manager.py` references the edit manager UI; the live spec is `docs/EDIT_MANAGER.md`
  and `docs/UI_ACTIONS_STANDARD.md`.
- Startup logs one line naming the commit, route count and database it is running
  (`Startup facts: commit=... routes=... database=...`). `logs/app.log` is the record of which
  migration touched which database file.
