# -*- coding: utf-8 -*-
"""معاينة PDF في استيراد المستندات.

يغطي:
* PDF بنص قابل للاستخراج (يُنتج مرشحين ويُعرض في الصفحة).
* PDF متعدد الصفحات (تُقرأ كل الصفحات).
* PDF ممسوح ضوئياً/بلا نص (خطأ واضح لا معاينة فارغة).
* PDF تالف وغير صالح (خطأ واضح).
* PDF مشفّر بكلمة مرور (خطأ واضح).
* Excel كما هو دون تراجع.
* ظهور أخطاء المعالجة للمستخدم في مسار HTML وفي مسار JSON.

بناء ملفات PDF هنا بالبايثون القياسي فقط (بلا مكتبة كتابة إضافية).
"""
from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401
from app.database import session as session_module
from app.database.base import Base
from app.modules.document_import.extraction.extractor import (
    ExtractionError,
    extract_document,
)
from app.modules.document_import.services import preview_from_document


# ---------------------------------------------------------------------------
# مولّدات PDF (stdlib فقط)
# ---------------------------------------------------------------------------
def build_pdf(pages_lines, font="Helvetica") -> bytes:
    """PDF صالح بسيط: قائمة صفحات، كل صفحة قائمة أسطر نصية."""
    objects = {}
    n = len(pages_lines)
    font_num = 3
    kids = [f"{4 + 2 * i} 0 R" for i in range(n)]
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = ("<< /Type /Pages /Kids [" + " ".join(kids) + f"] /Count {n} >>").encode()
    objects[font_num] = ("<< /Type /Font /Subtype /Type1 /BaseFont /" + font + " >>").encode()

    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    for i, lines in enumerate(pages_lines):
        pnum, cnum = 4 + 2 * i, 5 + 2 * i
        objects[pnum] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> /Contents {cnum} 0 R >>"
        ).encode()
        parts = ["BT", "/F1 12 Tf", "72 720 Td"]
        for j, line in enumerate(lines):
            if j > 0:
                parts.append("0 -18 Td")
            parts.append(f"({esc(line)}) Tj")
        parts.append("ET")
        content = "\n".join(parts).encode("latin-1")
        objects[cnum] = (
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    xref_pos = len(out)
    maxnum = max(objects)
    out += f"xref\n0 {maxnum + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, maxnum + 1):
        if num in offsets:
            out += f"{offsets[num]:010d} 00000 n \n".encode()
        else:
            out += b"0000000000 65535 f \n"
    out += (f"trailer\n<< /Size {maxnum + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)


def build_scanned_pdf() -> bytes:
    """صفحة بلا أي عملية نصية (يحاكي ملفاً ممسوحاً ضوئياً)."""
    content = b"0.2 0.2 0.2 rg\n50 50 500 700 re f"
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        4: b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    }
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {max(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for num in range(1, max(objects) + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {max(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)


def build_encrypted_pdf(password="secret") -> bytes:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(BytesIO(build_pdf([["Engine power: 250 kW"]])))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# استخراج PDF (وحدة الاستخراج)
# ---------------------------------------------------------------------------
def test_pdf_with_extractable_text_produces_candidates(tmp_path):
    p = tmp_path / "spec.pdf"
    p.write_bytes(build_pdf([["Engine power: 250 kW"]]))

    ex = extract_document(p)
    assert "Engine power" in ex.text
    assert "PAGE 1:" in ex.text

    cands = preview_from_document(model_id=1, file_path=p, db=None)
    match = next((c for c in cands if "Engine power" in (c.name_found or "")), None)
    assert match is not None
    assert match.value == "250"
    assert (match.unit or "").lower() == "kw"


def test_multi_page_pdf_extracts_every_page(tmp_path):
    p = tmp_path / "multi.pdf"
    p.write_bytes(build_pdf([["Engine power: 250 kW"], ["Gross weight: 5000 kg"]]))

    ex = extract_document(p)
    assert "PAGE 1:" in ex.text and "PAGE 2:" in ex.text
    assert "Engine power" in ex.text and "Gross weight" in ex.text
    assert extract_document(p).tables == []


def test_scanned_pdf_without_text_raises_clear_error(tmp_path):
    p = tmp_path / "scan.pdf"
    p.write_bytes(build_scanned_pdf())

    with pytest.raises(ExtractionError) as ei:
        extract_document(p)
    assert ei.value.reason == "pdf_no_text"
    assert "ممسوح" in ei.value.message


def test_corrupt_pdf_raises_clear_error(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nthis is not a valid pdf\x00\xff\xfe")

    with pytest.raises(ExtractionError) as ei:
        extract_document(p)
    assert ei.value.reason in ("pdf_corrupt", "pdf_no_text")
    assert ei.value.message


def test_encrypted_pdf_raises_clear_error(tmp_path):
    p = tmp_path / "enc.pdf"
    p.write_bytes(build_encrypted_pdf())

    with pytest.raises(ExtractionError) as ei:
        extract_document(p)
    assert ei.value.reason == "pdf_encrypted"
    assert "كلمة مرور" in ei.value.message


# ---------------------------------------------------------------------------
# Excel دون تراجع
# ---------------------------------------------------------------------------
def test_excel_preview_still_works(tmp_path):
    import openpyxl

    p = tmp_path / "spec.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["قدرة المحرك", "250 kW"])
    ws.append(["الوزن الإجمالي", "5000 kg"])
    wb.save(p)

    ex = extract_document(p)
    assert "قدرة المحرك" in ex.text
    cands = preview_from_document(model_id=1, file_path=p, db=None)
    assert any("قدرة المحرك" in (c.name_found or "") for c in cands)


# ---------------------------------------------------------------------------
# المسار الكامل عبر الراوتر (HTML + JSON) بقاعدة اختبار معزولة
# ---------------------------------------------------------------------------
@pytest.fixture
def client_and_ids():
    from web import main
    from app.core.security import hash_password
    from app.modules.users.models import User
    from app.modules.equipment_types.models import (
        EquipmentBrand,
        EquipmentCategory,
        EquipmentModel,
        EquipmentModelSpecDefinition,
        EquipmentType,
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    db = TestingSession()
    try:
        db.add(User(username="pdf-tester", full_name="مختبر PDF",
                    hashed_password=hash_password("Test@12345"), role="admin"))
        db.flush()
        cat = EquipmentCategory(name="حافلات PDF", code="BUSPDF", sort_order=1)
        db.add(cat)
        db.flush()
        brand = EquipmentBrand(name="Hyundai PDF", is_active=True)
        db.add(brand)
        db.flush()
        et = EquipmentType(name="حافلة صغيرة PDF", measurement_unit="كم", category_id=cat.id)
        db.add(et)
        db.flush()
        model = EquipmentModel(name="H100 PDF", equipment_type_id=et.id, brand_id=brand.id)
        db.add(model)
        db.flush()
        d1 = EquipmentModelSpecDefinition(
            name="قدرة المحرك", code="engine_power_pdf", data_type="number",
            unit="kW", sort_order=1,
        )
        db.add(d1)
        db.commit()
        ids = {"model_id": model.id, "def_id": d1.id}
    finally:
        db.close()

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(main, "init_db", lambda: None)
        patch.setattr(main, "create_default_admin", lambda: None)
        patch.setattr(session_module, "SessionLocal", TestingSession)

        app = main.create_app()
        app.dependency_overrides[session_module.get_db] = override_get_db

        with TestClient(app) as c:
            r = c.post("/login", data={"username": "pdf-tester", "password": "Test@12345"},
                       follow_redirects=False)
            assert r.status_code in (302, 303), r.text
            yield c, ids


def test_html_preview_shows_pdf_candidates(client_and_ids):
    c, ids = client_and_ids
    r = c.post(
        "/document-import/preview",
        data={"model_id": str(ids["model_id"])},
        files={"file": ("spec.pdf", build_pdf([["Engine power: 250 kW"]]), "application/pdf")},
    )
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Engine power" in r.text
    assert "/document-import/apply" in r.text  # يُعرض نموذج المراجعة/التطبيق
    assert "تعذّرت المعاينة" not in r.text


def test_html_preview_shows_empty_state_instead_of_silent_blank(client_and_ids):
    c, ids = client_and_ids
    # نص بلا أي زوج "اسم: قيمة" ولا جدول => صفر مرشحين دون خطأ
    r = c.post(
        "/document-import/preview",
        data={"model_id": str(ids["model_id"])},
        files={"file": ("plain.pdf", build_pdf([["Hello world nothing here"]]), "application/pdf")},
    )
    assert r.status_code == 200
    assert "تعذّرت المعاينة" not in r.text
    assert "لم يُعثر على أي خصائص" in r.text
    assert "/document-import/apply" not in r.text


def test_html_preview_surfaces_scanned_pdf_error(client_and_ids):
    c, ids = client_and_ids
    r = c.post(
        "/document-import/preview",
        data={"model_id": str(ids["model_id"])},
        files={"file": ("scan.pdf", build_scanned_pdf(), "application/pdf")},
    )
    assert r.status_code == 200
    assert "تعذّرت المعاينة" in r.text
    assert "لم يُعثر على نص" in r.text
    assert "/document-import/apply" not in r.text  # لا نموذج تطبيق فارغ


def test_html_preview_surfaces_corrupt_pdf_error(client_and_ids):
    c, ids = client_and_ids
    r = c.post(
        "/document-import/preview",
        data={"model_id": str(ids["model_id"])},
        files={"file": ("bad.pdf", b"%PDF-1.4\nnot a real pdf\x00\xff\xfe", "application/pdf")},
    )
    assert r.status_code == 200
    assert "تعذّرت المعاينة" in r.text
    assert ("تالف" in r.text) or ("لم يُعثر على نص" in r.text)
    assert "/document-import/apply" not in r.text


def test_json_preview_pdf_ok_and_scanned_error(client_and_ids):
    c, ids = client_and_ids
    ok = c.post(
        "/document-import/preview/json",
        data={"model_id": str(ids["model_id"])},
        files={"file": ("spec.pdf", build_pdf([["Engine power: 250 kW"]]), "application/pdf")},
    )
    assert ok.status_code == 200
    assert any("Engine power" in (x["name_found"] or "") for x in ok.json()["candidates"])

    bad = c.post(
        "/document-import/preview/json",
        data={"model_id": str(ids["model_id"])},
        files={"file": ("scan.pdf", build_scanned_pdf(), "application/pdf")},
    )
    assert bad.status_code == 400
    assert "لم يُعثر على نص" in bad.json()["detail"]


def test_html_preview_excel_unaffected(client_and_ids):
    import openpyxl

    c, ids = client_and_ids
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["قدرة المحرك", "250 kW"])
    ws.append(["الوزن الإجمالي", "5000 kg"])
    buf = BytesIO()
    wb.save(buf)

    r = c.post(
        "/document-import/preview",
        data={"model_id": str(ids["model_id"])},
        files={"file": (
            "spec.xlsx", buf.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )},
    )
    assert r.status_code == 200
    assert "قدرة المحرك" in r.text
    assert "تعذّرت المعاينة" not in r.text
    assert "/document-import/apply" in r.text


def test_model_specs_view_offers_document_import_for_selected_model(client_and_ids):
    c, ids = client_and_ids

    page = c.get("/equipment-types")
    assert page.status_code == 200, page.text
    assert 'id="btn-import-specs-doc-view"' in page.text
    assert "importSpecsLink.href='/document-import/upload?model_id='+encodeURIComponent(id)" in page.text

    upload = c.get("/document-import/upload", params={"model_id": ids["model_id"]})
    assert upload.status_code == 200, upload.text
    assert f'name="model_id" value="{ids["model_id"]}"' in upload.text
