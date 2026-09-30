# PROJECT_MAP — Materiel Fleet Management

> External memory for the three protocols: **Planning → Execution → Surgical Editing**.
> Last synced: **2026-09-30** · branch `stage3-maintenance-operations` (10 ahead of origin, not pushed).
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
web/main.py  create_app()  (lifespan: configure_logging → init_db() → create_default_admin → shutdown_logging)
  ├─ app/core/        config · logging · dependencies · permissions · security · templating
  ├─ app/database/    base · session · init_db · model_registry
  ├─ app/modules/     14 domains, each: models · schemas · services · router · templates
  │     equipment_types (32 handlers) · maintenance (27) · faults_repairs (17+9)
  │     equipment (14) · meter_readings (9+1) · tires (9) · users (8) · batteries (7)
  │     fuel (3) · equipment_maintenance (4) · missions (2) · dashboard (1)
  ├─ app/modules/asset_movements/   shared policy helpers (NO router) — used by tires + batteries + tests
  ├─ app/modules/notifications/     aggregator + providers (registered on package import)
  ├─ migrations/versions/           52 revisions
  └─ tests/                         61 files / 271 tests; template-contract tests pin exact markup/IDs
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

---

## [ORPHANS & PENDING]

1. ~~`notifications` module had 0 importers~~ — **resolved**: providers + dashboard panel (see [ARCHITECTURE]).
2. `asset_movements` has no router/API — assumed intentional (policy helpers only). **Still unconfirmed by user.**
3. ~~`README.md` was a 79 KB auto-update log~~ — **resolved**: real README (old content recoverable from git history).
4. `tests/test_run_web_smoke.py::test_official_run_web_starts_and_serves_login` is environment-dependent: it fails whenever port 8000 is already served. Passes when the port is free.
5. ~~Dependency lag~~ — **resolved** in M4; keep the `bcrypt` pin rationale.
6. ~~Untracked `design_mockup.html` / `server.log`~~ — **resolved**: added to `.gitignore` (never committed).
7. Branch `stage3-maintenance-operations` is 16 commits ahead of origin — **push is on hold by user instruction**.
8. ~~Logging not implemented~~ — **resolved** in M1.
9. **Page rendering is not covered by pytest.** The authenticated smoke (login → 17 pages) lives in a throwaway script and caught two production-breaking bugs during M4. Promoting it to a real test (auth fixture + seeded DB) is the highest-value next step; needs a decision because it means adding test fixtures for auth.
10. `faults_repairs/templates/fault_detail.html` renders the raw repair status key (`{{ r.status }}`) inside an Arabic interface. Same defect class as the dashboard status card (fixed in `fd3b2c4`), different page — left unfixed to keep the edit scope tight.
11. Operational status labels are duplicated as `if/elif` chains in at least five places (`equipment_list`, `equipment_detail`, `equipment_numerical_status` template + its JS, `dashboard`). Unifying them is an architectural decision, not a cleanup: every module builds its own Jinja environment through `get_module_templates`, so there is no single place to inject a shared label map today.
12. The dashboard status cards were the only place showing a raw enum key, but other raw keys may still exist in pages not yet visually reviewed. A pass over the remaining 42 templates is the systematic fix.