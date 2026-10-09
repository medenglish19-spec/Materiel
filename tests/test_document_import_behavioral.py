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
        def first(self): return type('M', (), {})()
        def add(self, obj): self.added.append(obj)
        def commit(self): self.committed = True

    db = DummySession()
    cands = [
        ImportApplyItem(definition_id=1, value="150", unit="kW", is_new=False, approved=False, ignored=False, edited=False),
        ImportApplyItem(definition_id=None, value="10", is_new=True, approved=True, ignored=False, edited=False),
        ImportApplyItem(definition_id=5, value="12", is_new=False, approved=True, ignored=False, edited=True, value_edited="12"),
    ]
    res = services.apply_candidates(1, cands, db)
    assert res['added'] == 1
    assert res['skipped_new'] >= 1
    assert res['skipped_ignored'] >= 1
    assert db.committed
