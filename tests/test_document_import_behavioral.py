from pathlib import Path
import tempfile
import os

from app.database import model_registry  # noqa: F401  (registers all mappers)


class _Stub:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class DummySession:
    """Minimal stubs that mimic the three queries apply_candidates performs."""

    def __init__(self):
        from app.modules.equipment_types.models import (
            EquipmentModel,
            EquipmentModelSpecDefinition,
            EquipmentModelSpecValue,
            EquipmentType,
            EquipmentCategory,
        )

        self._EquipmentModel = EquipmentModel
        self._Definition = EquipmentModelSpecDefinition
        self._Value = EquipmentModelSpecValue
        self._EquipmentType = EquipmentType
        self._Category = EquipmentCategory
        self.committed = False
        self.rolled_back = False
        self.added = []
        self._entity = None

    def query(self, *entities):
        self._entity = entities[0] if entities else None
        return self

    def options(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def filter_by(self, *a, **k):
        return self

    def first(self):
        if self._entity is self._EquipmentModel:
            # model with a linked equipment type, as the real flow requires
            return _Stub(
                id=1,
                name="H100",
                equipment_type_id=7,
                equipment_type=_Stub(id=7, category_id=3),
            )
        if self._entity is self._Definition:
            # pre-load finds nothing, so the new candidate follows the create path
            return None
        if self._entity in (self._EquipmentType, self._Category):
            # referenced type/category must resolve so creation proceeds
            return _Stub(id=7, category_id=3, name="stub")
        # no EquipmentModelSpecValue row yet -> insert path
        return None

    def all(self):
        # no pre-existing definitions in the cache
        return []

    def count(self):
        return 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_services_apply_requires_approval_and_def():
    from app.modules.document_import import services
    from app.modules.document_import.schemas import ImportApplyItem

    db = DummySession()
    cands = [
        ImportApplyItem(definition_id=1, value="150", unit="kW", is_new=False, approved=False, ignored=False, edited=False),
        ImportApplyItem(definition_id=None, name_found="خاصية جديدة", value="10", is_new=True, approved=True, ignored=False, edited=False),
        ImportApplyItem(definition_id=5, value="12", is_new=False, approved=True, ignored=False, edited=True, value_edited="12"),
    ]
    res = services.apply_candidates(1, cands, db)
    assert "results" in res
    assert "summary" in res
    # One approved existing definition (cands[2] with def_id=5, approved=True, edited=True) -> applied
    # One new approved (cands[1]) -> created_definition 
    # One not approved (cands[0] approved=False) -> not_approved
    assert res['summary']['applied'] == 1
    assert res['summary']['created_definition'] == 1
    assert res['summary']['not_approved'] == 1
    assert db.committed
