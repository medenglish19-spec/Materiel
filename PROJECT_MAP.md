# PROJECT_MAP — Materiel Fleet Management

> External memory for the three protocols: **Planning → Execution → Surgical Editing**.
> Last synced: **2026-09-30** · branch `stage3-maintenance-operations` (**3 local commits not pushed yet**: labels, page tests, startup security warnings).
> Authoritative business rules live in `docs/MATERIEL_EXECUTION_MAP.md` — read it before touching any module.

---

## [TECH_STACK]

**Runtime:** Python 3.14.6 local · **CI runs Python 3.11** · Windows · PowerShell 5.1 · SQLite (`fleet_assets.db`)

| Layer | Package | Pinned | Latest stable (PyPI, 2026-09-30) | Status |
|---|---|---|---|---|
| Web | fastapi | 0.142.2 | 0.142.2 | current |
| Web | starlette (transitive) | 1.7.0 | 1.7.0 | current |
| Server | uvicorn[standard] | 0.54.0 | 0.54.0 | current |
| ORM | sqlalchemy | 2.1.1 | 2.1.1 | current |
| Migrations | alembic | 1.20.0 | 1.20.0 | current |
| Templates | jinja2 | 3.1.6 | 3.1.6 | current |
| Validation | pydantic | 2.13.5 | 2.13.5 | current |
| Forms | python-multipart | 0.0.32 | 0.0.32 | current |
| JWT | python-jose | 3.5.0 | 3.5.0 | current |
| Hashing | passlib[bcrypt] | 1.7.4 | 1.7.4 | current, unmaintained upstream |
| Hashing | bcrypt | 4.0.1 | 5.0.0 | **intentionally pinned** |
| Excel | openpyxl | 3.1.5 | 3.1.5 | current |
| Tests | pytest / httpx | 9.1.1 / 0.28.1 | 9.1.1 / 0.28.1 | current |

- `bcrypt==4.0.1` is a deliberate pin: `passlib 1.7.4` breaks on bcrypt ≥ 4.1
  (`__about__` was removed). Do not "fix" the lag without replacing passlib.
- No Node/npm front end: vanilla JS in `static/js/` (2 files), CSS in `static/css/style.css` + inline shell in `web/templates/base.html`.
- UI: Jinja2, RTL, 43 templates.
- CI: `.github/workflows/python-package-conda.yml` (filename check → `compileall` → SQLite 0007 recovery → `pytest`).

### Framework contract change (FastAPI ≥ 0.142 / Starlette 1.7)

Three breaking changes were found by the M4 upgrade and fixed:

1. **`TemplateResponse` signature** — the legacy positional form
   `TemplateResponse(name, context)` was removed; it silently passed the context
   dict as the template name and crashed with
   `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')`
   inside the Jinja cache. All 39 call sites now use
   `TemplateResponse(request=request, name=..., context=...)`.
   `users/router.py` already used the new form.
2. **`app.routes` shape** — `include_router` is wrapped in `_IncludedRouter`
   (no `.path`). Path enumeration must walk `route.original_router.routes` with
   `route.include_context.prefix`; see `_registered_paths()` in
   `tests/test_navigation_and_routes.py`.
3. **SQLAlchemy 2.1 is stricter** — `filter(... if cond else [])` raised
   `ArgumentError: SQL expression for WHERE/HAVING role expected, got []`
   (`missions/services.py`). Fixed by skipping the filter when there are no
   missions; covered by `tests/test_mission_status_sync.py`.

Verification for any of these: full pytest suite **plus** an authenticated
page smoke over all 17 pages — `pytest` alone does not render them.

---

## [SYSTEM_FLOW]

Each numbered step is a goal that must stay verifiable after any change:

1. **Login** → JWT cookie → `/` redirects to `/dashboard`.
2. **Master data** `/equipment-types` → Category → Equipment Type → Model (specs, tire/battery config, image).
3. **Equipment** `/equipment` → CRUD attached to a Model; operational + technical status.
4. **Transactions** → meter readings, missions, fuel, faults → repairs, tire/battery install-remove.
5. **Maintenance** → rules live on **Model**, records live on **Equipment**, due by meter (km/h) or calendar.
6. **Derived state** → history → current state → calculations → **notifications** → dashboard indicators.
7. **Errors** → HTML POST failures redirect back with `?notice=` banner; API calls get JSON.
   All non-static responses are `Cache-Control: no-cache`.

Guard rails: `Source Data → Domain Service → Aggregation → Page`. Dashboard is never a source of truth.

---

## [ARCHITECTURE]

```
web/main.py  create_app()  (lifespan: configure_logging → init_db() → create_default_admin → security_warnings() → shutdown_logging)
  ├─ app/core/        config · logging · dependencies · permissions · security · templating
  ├─ app/database/    base · session · init_db · model_registry
  ├─ app/modules/     14 domains, each: models · schemas · services · router · templates
  │     equipment_types (32 handlers) · maintenance (27) · faults_repairs (17+9)
  │     equipment (14) · meter_readings (9+1) · tires (9) · users (8) · batteries (7)
  │     fuel (3) · equipment_maintenance (4) · missions (2) · dashboard (1)
  ├─ app/modules/asset_movements/   shared policy helpers (NO router) — confirmed intentional, see [ORPHANS] #2
  ├─ app/modules/notifications/     aggregator + providers (registered on package import)
  ├─ migrations/versions/           52 revisions
  └─ tests/                         65 files / 320 tests (319 passed, 1 skipped); template-contract tests pin exact markup/IDs
```

### Notifications layer (wired 2026-09-30)

- `services.py` — provider registry (`register_provider`) + `get_all_notifications(db)`:
  merges by `key`, keeps the highest severity, sorts overdue → upcoming.
- `providers.py` — three providers, each calling its owning domain's services:
  maintenance due (`maintenance.services.status_for`), expired installed tires
  (`tires.batch_state.current_states`), installed batteries past due date
  (`batteries.services.replacement_due_date`).
- Consumer: `dashboard_page()` → `notifications` in context → "التنبيهات الموحّدة" panel.
- Note: the tire/battery batch queries now run twice per dashboard render (tables + notifications) — accepted cost of the aggregator design.

### Effective operational status (merged + batched 2026-09-30)

- `equipment/services.py` — one rule, two entry points:
  `active_mission_equipment_ids()` (one query per 500 ids) → `_effective_status()`
  (the single source of truth) → `effective_operational_status()` (one item) and
  `effective_operational_statuses()` (whole page).
- Rule order: `technical_condition == "broken"` → `unavailable`; a stored
  maintenance/workshop/unavailable status is kept as is; otherwise an active
  mission (`start <= today` and `end is null or end > today`) → `in_mission`,
  else `available`.
- `equipment_page()` passes `operational_statuses` to the card template, which
  resolves `{% set current_status = operational_statuses[item.id] %}` per loop.
  Never display the stored `item.operational_status` in that list.
- **Caveat:** the dashboard status cards still count the *stored* field
  (`count_by_operational_status`). It is kept correct only because
  `missions.services.add_mission` sets `in_mission` on creation and
  `sync_mission_statuses` (run by the `/missions` page) demotes finished ones.
  Two pages, two rules — see [ORPHANS] #14.

### Arabic label registry (added 2026-09-30)

- `app/core/labels.py` — the only place an enum key becomes Arabic:
  `OPERATIONAL_STATUS_LABELS`, `TECHNICAL_CONDITION_LABELS`,
  `FAULT_STATUS_LABELS`, `REPAIR_STATUS_LABELS`, `SEVERITY_LABELS`,
  plus `label(kind, value)` (unknown key → itself, never raises) and
  `label_options(kind)`.
- Injected once in `app/core/templating.py::get_module_templates()` — the only
  Jinja env factory in the project — as globals `label`, `label_options`, `LABELS`.
  JavaScript reads `window.MATERIEL_LABELS = {{ LABELS | tojson }}`.
- `tests/test_labels.py` enforces the rules: every schema key has a label, no
  template keeps a duplicated `if/elif` chain or an inline label dict.
- Deliberate exception: `equipment_meters.html` and `meter_readings_list.html`
  answer "is it working?" (yes/no), not "where is it?" — they keep a binary
  label. Pinned by a test.
- One visible wording change: repairs `completed` reads "تم الإصلاح" everywhere
  (was "مكتمل" on the list) so one status has one wording.

### Page rendering tests (added 2026-09-30)

- `tests/test_authenticated_pages.py` — in-memory DB seeded through the real
  services, real login form, then 20 pages + 5 detail pages.
- Isolation is doubled on purpose: `dependency_overrides[get_db]` for routers,
  and a patched `SessionLocal` for the modules that open their own session
  inside a function (`meter_readings/audit.py`), so a test can never read
  `fleet_assets.db`.
- The seed creates the mission via `missions.services.add_mission`, not a raw
  INSERT: only that path sets `operational_status = in_mission`, so a raw
  insert would test a state the app can never produce.

### Startup security warnings (added 2026-09-30)

- `app/core/config.py::security_warnings(db_path)` — read-only check, logged as
  `[security] WARNING` at startup: default `SECRET_KEY` (anyone with the source
  can forge a session) and `admin` still on the seeded password.
- **Decision: it warns, it never blocks.** The user keeps `admin/Admin@123`
  working locally, so startup is not refused and the hash is never rewritten.
  Any failure inside the check is swallowed — a locked database must not stop
  the app from booting.

---

## [LOGGING] (implemented)

`app/core/logging.py` — non-blocking by construction:

- `QueueHandler` on the root logger: `put_nowait` into memory, no I/O in the request path.
- One `QueueListener` thread → stderr + rotating `logs/app.log` (1 MB × 3, UTF-8).
- `enqueue` never raises; levels DEBUG/INFO/WARNING/ERROR; `LOG_LEVEL`, `LOG_DIR` from env.
- `configure_logging()` is idempotent and restart-safe (output handlers are built once, so repeated app lifecycles do not leak file handles); `shutdown_logging()` drains the queue then stops.
- Contract: no `print()` anywhere in `app/` (`tests/test_logging.py`).

---

## [MILESTONES] (verifiable goals)

| # | Goal | Success criterion | State |
|---|---|---|---|
| M0 | Baseline is green | `pytest -q` → 250 passed, 1 skipped | ✅ 2026-09-30 |
| M1 | Async logging layer | queue-backed logger, `print()` count in `app/` = 0, suite green | ✅ 268 passed |
| M2 | Notifications wired to dashboard | 3 providers registered, merged by severity, panel rendered | ✅ 268 passed |
| M3 | Docs rebuilt | real `README.md` (run / test / login / map pointers) | ✅ |
| M4 | Dependency upgrades | pinned == latest, `pip check` clean, full suite green, page smoke | ✅ 271 passed · 17/17 pages 200 |
| M5 | Labels unified + pages under pytest | one Arabic label registry; 25 pages render in `pytest`; startup warns on insecure defaults | ✅ 319 passed, 1 skipped |

---

## [ORPHANS & PENDING]

1. ~~`notifications` module had 0 importers~~ — **resolved**: providers + dashboard panel (see [ARCHITECTURE]).
2. ~~`asset_movements` has no router/API~~ — **resolved by inspection, not by guess**: it is a **shared policy module**, used in two production routers (`tires/router.py:109,111` and `batteries/router.py:83,85`) and covered by 4 tests. It enforces rules that `docs/MATERIEL_EXECUTION_MAP.md:174-178` states as authoritative — "Move = Remove + Install" (a direct `move` is rejected) and "no overwriting an old install record to hide history" (install is blocked while one is still registered). Deleting it would break both routers; keep it.
3. ~~`README.md` was a 79 KB auto-update log~~ — **resolved**: real README (old content recoverable from git history).
4. `tests/test_run_web_smoke.py::test_official_run_web_starts_and_serves_login` is environment-dependent: it fails whenever port 8000 is already served. Passes when the port is free.
5. ~~Dependency lag~~ — **resolved** in M4; keep the `bcrypt` pin rationale.
6. ~~Untracked `design_mockup.html` / `server.log`~~ — **resolved**: added to `.gitignore` (never committed).
7. ~~Branch was ahead of origin~~ — **resolved** 2026-09-30: pushed after rebasing onto the 3 upstream commits (`582a56e`).
8. ~~Logging not implemented~~ — **resolved** in M1.
9. ~~Page rendering is not covered by pytest~~ — **resolved**: `tests/test_authenticated_pages.py` (7 tests) builds an isolated in-memory DB, seeds it through the real services, logs in over the real form, and asserts 200 + a module marker for 20 pages, plus 5 detail pages that no check had ever rendered (`/equipment/{id}`, `/meters`, `/edit`, fault detail, repair detail). A failure lists every offending path at once. Unauthenticated access is asserted to never return 200.
10. ~~`fault_detail.html` renders the raw repair status key~~ — **resolved** with the label registry: the whole faults module now translates status, repair status and severity, and no raw key survives in the rendered markup (asserted by the page tests).
11. ~~Operational status labels are duplicated as `if/elif` chains in five places~~ — **resolved**: `app/core/labels.py` is the single source, injected through the one Jinja env factory. The premise that "there is no single place to inject a shared map" was wrong: all 13 modules build their environment through `get_module_templates()`.
12. A pass over the remaining templates for raw enum keys is still open. The faults module and all equipment status pages are now covered; what remains is one `if/elif` chain for `exploitation_impact` (fault detail) and the less-reviewed modules. Note: that chain renders correctly today — it is duplication, not a visible bug.
13. ~~`effective_operational_status()` had no unit test and `/equipment` had an N+1~~ — **resolved**: `effective_operational_statuses(db, items)` computes the whole page in one mission query (measured 200 items: 200 queries → 1, identical results), the single-item function delegates to the same rule helper, and `tests/test_effective_operational_status.py` covers the rules (broken, workshop/maintenance override, running / finished / not-started / ends-today mission) plus a query-count guard.
14. **The dashboard and the equipment list compute the status two different ways.** `/equipment` shows the effective status (mission beats a stale `available`), while the dashboard counts the stored `operational_status`. Correct today only because `add_mission` sets `in_mission` and the `/missions` page demotes finished missions — a mission closed by anything else leaves the dashboard count stale until someone opens `/missions`. Deciding this is a semantics call (does the dashboard count intent or reality?), not a cleanup, so it was recorded rather than changed. Fix would be a batch call to `effective_operational_statuses` in the dashboard router.