import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.maintenance.models import MaintenanceOperation, MaintenanceOperationGroup
from app.modules.maintenance.router import api_operation_group_delete, router


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[MaintenanceOperationGroup.__table__, MaintenanceOperation.__table__])
    return sessionmaker(bind=engine)()


def test_operation_group_delete_route_exists():
    paths = {(route.path, tuple(sorted(route.methods or ()))) for route in router.routes}
    assert ("/api/maintenance/operation-groups/{group_id}", ("DELETE",)) in paths


def test_delete_group_keeps_operations_without_group():
    db = _session()
    try:
        group = MaintenanceOperationGroup(name="زيوت", sort_order=0)
        db.add(group)
        db.flush()
        operation = MaintenanceOperation(name="تغيير زيت", interval_days=30, group_id=group.id)
        db.add(operation)
        db.commit()
        group_id, operation_id = group.id, operation.id
        api_operation_group_delete(group_id, db=db, current_user=None)
        db.expire_all()
        assert db.get(MaintenanceOperationGroup, group_id) is None
        assert db.get(MaintenanceOperation, operation_id).group_id is None
    finally:
        db.close()


def test_delete_missing_group_returns_404():
    db = _session()
    try:
        with pytest.raises(HTTPException) as exc:
            api_operation_group_delete(999, db=db, current_user=None)
        assert exc.value.status_code == 404
    finally:
        db.close()
