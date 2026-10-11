from pathlib import Path
import tempfile
import os

def test_services_apply_requires_approval_and_def():
    from app.modules.document_import import services
    from app.modules.document_import.schemas import ImportApplyItem

    class DummySession:
        def __init__(self):
            self.committed = False
            self.added = []
        def query(self, *a, **k): return self
        def filter(self, *a, **k): return self
        def first(self): return type('M', (), {'id': 1, 'unit': 'kW', 'name': 'Test Definition'})()
        def all(self): return []
        def add(self, obj): self.added.append(obj)
        def commit(self): self.committed = True
        def rollback(self): pass

    db = DummySession()
    cands = [
        ImportApplyItem(definition_id=1, value="150", unit="kW", is_new=False, approved=False, ignored=False, edited=False),
        ImportApplyItem(definition_id=None, value="10", is_new=True, approved=True, ignored=False, edited=False),
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
