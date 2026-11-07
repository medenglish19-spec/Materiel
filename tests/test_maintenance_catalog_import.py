"""The retired maintenance PDF import endpoints stay unavailable.

Legacy imported rows remain in the database schema so upgrades preserve user data.
The supported Excel operation-library import routes remain available.
"""

from app.modules.maintenance.models import MaintenanceCatalogImport
from app.modules.maintenance.router import router as maintenance_router


def test_maintenance_pdf_catalog_import_routes_are_removed_but_excel_import_remains():
    registered = {route.path for route in maintenance_router.routes if getattr(route, "path", None)}

    assert not any(path.startswith("/maintenance/catalog-imports") for path in registered)
    assert {"/maintenance/rules/import", "/maintenance/rules/import-general"} <= registered
    assert MaintenanceCatalogImport.__tablename__ == "maintenance_catalog_imports"
