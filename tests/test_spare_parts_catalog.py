import io
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.modules.faults_repairs.models import SparePart
from app.modules.spare_parts_catalog import services
from app.modules.spare_parts_catalog.models import SparePartCatalogDetails, SparePartCatalogImport, SparePartCatalogReference


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_csv_preserves_leading_zero_reference_and_apply_is_idempotent(db):
    data = "Référence;Désignation;Fabricant;Catégorie\n001234;Filtre à air;Marque A;Moteur / Filtres\n".encode("utf-8-sig")
    batch = services.create_import_preview(db, "pieces.csv", data)
    db.commit()
    rows = services.preview_data(batch)["rows"]
    assert rows[0]["reference"] == "001234"
    assert rows[0]["name"] == "Filtre à air"
    result = services.apply_import(db, batch.id, {"row-0-include": "1"})
    assert result["added"] == 1
    part = db.query(SparePart).one()
    assert part.receiving_document is None
    assert part.part_number.startswith("CAT-")
    assert db.query(SparePartCatalogReference).one().reference == "001234"
    assert db.query(SparePartCatalogDetails).one().manufacturer == "Marque A"
    assert services.apply_import(db, batch.id, {"row-0-include": "1"}) == result
    assert db.query(SparePart).count() == 1


def test_reference_duplicate_is_flagged_and_never_merged_automatically(db):
    first = services.create_import_preview(db, "one.csv", b"reference,name,manufacturer\nA-1,Part One,Maker\n")
    db.commit()
    services.apply_import(db, first.id, {"row-0-include": "1"})
    second = services.create_import_preview(db, "two.csv", b"reference,name,manufacturer\nA-1,Part Other,Maker\n")
    db.commit()
    assert services.preview_data(second)["rows"][0]["duplicate"] == "exact"
    skipped = services.apply_import(db, second.id, {"row-0-include": "1"})
    assert skipped["added"] == 0
    assert db.query(SparePart).count() == 1


def test_xlsx_header_mapping_and_numeric_zero_format():
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Référence", "Désignation", "Fabricant"])
    sheet.append([1234, "Courroie", "Maker"])
    sheet["A2"].number_format = "000000"
    output = io.BytesIO()
    workbook.save(output)
    records, file_type, _ = services._parse_content("catalog.xlsx", output.getvalue())
    assert file_type == ".xlsx"
    assert records[0]["reference"] == "001234"


def test_xml_and_html_table_adapters_parse_rows():
    xml_rows, _, _ = services._parse_content("catalog.xml", b"<items><item><reference>01</reference><name>Valve</name></item></items>")
    html_rows, _, _ = services._parse_content("catalog.html", b"<table><tr><th>Reference</th><th>Name</th></tr><tr><td>02</td><td>Seal</td></tr></table>")
    assert xml_rows[0]["reference"] == "01"
    assert html_rows[0]["name"] == "Seal"


def test_docx_table_adapter_uses_local_openxml_extractor():
    document_xml = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Reference</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Name</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>D-1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Gasket</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as docx:
        docx.writestr("word/document.xml", document_xml)
    rows, _, _ = services._parse_content("catalog.docx", archive.getvalue())
    assert rows[0]["reference"] == "D-1"
    assert rows[0]["name"] == "Gasket"


def test_zip_catalog_is_read_without_extracting_and_rejects_traversal():
    safe = io.BytesIO()
    with zipfile.ZipFile(safe, "w") as archive:
        archive.writestr("catalog.csv", "reference,name\nX1,Part X\n")
        archive.writestr("image.bin", b"ignored")
    rows, extension, warnings = services._parse_content("catalog.zip", safe.getvalue())
    assert extension == ".zip"
    assert rows[0]["reference"] == "X1"
    assert warnings

    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../outside.csv", "reference,name\nX1,Part X\n")
    with pytest.raises(ValueError, match="غير آمن"):
        services._parse_content("bad.zip", malicious.getvalue())


def test_zip_image_is_previewed_and_attached_only_by_exact_reference(db, monkeypatch):
    pillow = pytest.importorskip("PIL.Image")
    png = io.BytesIO()
    pillow.new("RGB", (2, 2), color=(20, 80, 120)).save(png, format="PNG")
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("catalog.csv", "reference,name\n0012,Part with image\n")
        archive.writestr("images/0012.png", png.getvalue())
        archive.writestr("images/unmatched.png", png.getvalue())
    batch = services.create_import_preview(db, "catalog.zip", archive_bytes.getvalue())
    db.commit()
    record = services.preview_data(batch, include_images=True)["rows"][0]
    assert record["image_data"]
    assert record["image_name"] == "0012.png"
    monkeypatch.setattr(services, "store_image", lambda _data, _name: "/static/uploads/spare-parts/test.png")
    monkeypatch.setattr(services, "remove_image", lambda _path: None)
    services.apply_import(db, batch.id, {"row-0-include": "1", "row-0-image-data": record["image_data"]})
    details = db.query(SparePartCatalogDetails).one()
    assert details.image_path == "/static/uploads/spare-parts/test.png"
    assert "image_data" not in services.preview_data(batch)["rows"][0]


@pytest.mark.parametrize("filename,data", [
    ("fake.xlsx", b"reference,name\nA,Part\n"),
    ("bad.csv", b"only-one-column\n"),
])
def test_invalid_or_unrecognized_catalogs_fail_clearly(filename, data):
    with pytest.raises(ValueError):
        services._parse_content(filename, data)


def test_unavailable_optional_formats_report_the_missing_dependency():
    with pytest.raises(ValueError, match="xlrd"):
        services._parse_content("old.xls", bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy")
