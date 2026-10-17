from pathlib import Path
import io


def test_document_import_module_exists():
    assert Path("app/modules/document_import").exists()
    assert Path("app/modules/document_import/router.py").exists()
    assert Path("app/modules/document_import/services.py").exists()
    assert Path("app/modules/document_import/extraction/extractor.py").exists()
    assert Path("app/modules/document_import/parsing/parser.py").exists()
    assert Path("app/modules/document_import/matching/matcher.py").exists()
    assert Path("app/modules/document_import/normalization/normalizer.py").exists()


def test_router_has_endpoints():
    s = Path("app/modules/document_import/router.py").read_text(encoding="utf-8", errors="replace")
    assert "/document-import/preview" in s
    assert "/document-import/apply" in s


def test_services_have_real_logic():
    s = Path("app/modules/document_import/services.py").read_text(encoding="utf-8", errors="replace")
    assert "preview_from_document" in s
    assert "apply_candidates" in s
    assert "extract_document" in s
    assert "match_against_definitions" in s


def test_extractor_offline_refs():
    s = Path("app/modules/document_import/extraction/extractor.py").read_text(encoding="utf-8", errors="replace")
    assert "docling" in s.lower() or "pypdf" in s.lower()


def test_schemas_have_review_fields():
    s = Path("app/modules/document_import/schemas.py").read_text(encoding="utf-8", errors="replace")
    assert "approved" in s
    assert "ignored" in s
    assert "edited" in s
    assert "ImportApplyRequest" in s
    assert "ImportApplyItem" in s


def test_document_import_forms_join_the_shared_edit_manager():
    template = Path("app/modules/document_import/templates/upload.html").read_text(encoding="utf-8")
    assert 'id="previewForm"' in template and 'id="previewForm" action="/document-import/preview" method="post" enctype="multipart/form-data" data-em-root' in template
    assert 'id="applyForm"' in template and 'id="applyForm" method="post" action="/document-import/apply" style="margin-top:16px" data-em-root' in template
