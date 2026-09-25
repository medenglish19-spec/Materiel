import json
from pathlib import Path
from types import SimpleNamespace

from jinja2 import DictLoader, Environment
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types import router, services
from app.modules.equipment_types.models import EquipmentCategory, EquipmentType
from app.modules.equipment_types.schemas import EquipmentCategoryCreate, EquipmentTypeCreate


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def _session():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session()


def test_category_update_form_preserves_code():
    db = _session()
    try:
        category = services.create_category(
            db, EquipmentCategoryCreate(name="الفئة الأصلية", code="C-100")
        )
        router.update_category_form(
            category.id,
            name="الفئة المعدلة",
            code="C-100",
            db=db,
            current_user=object(),
        )
        db.expire_all()
        saved = services.get_category(db, category.id)
        assert saved.name == "الفئة المعدلة"
        assert saved.code == "c-100"
    finally:
        db.close()


def test_type_update_form_preserves_category_measurement_unit_and_quantity():
    db = _session()
    try:
        category = services.create_category(
            db, EquipmentCategoryCreate(name="فئة النوع", code="C-200")
        )
        equipment_type = services.create_type(
            db,
            EquipmentTypeCreate(
                name="نوع أصلي",
                measurement_unit="hours",
                category_id=category.id,
                theoretical_quantity=10,
            ),
        )
        router.update_type_form(
            equipment_type.id,
            name="نوع معدل",
            measurement_unit="hours",
            category_id=category.id,
            theoretical_quantity="10",
            technical_library_category_id="",
            technical_library_type_id="",
            db=db,
            current_user=object(),
        )
        db.expire_all()
        saved = services.get_type(db, equipment_type.id)
        assert saved.name == "نوع معدل"
        assert saved.measurement_unit == "hours"
        assert saved.category_id == category.id
        assert saved.theoretical_quantity == 10
    finally:
        db.close()


def test_master_data_template_renders_reference_fields_into_tree_nodes():
    template_path = Path("app/modules/equipment_types/templates/master_data_workspace.html")
    template = template_path.read_text(encoding="utf-8")
    env = Environment(
        loader=DictLoader(
            {
                "base.html": "{% block title %}{% endblock %}{% block content %}{% endblock %}",
                "master_data_workspace.html": template,
            }
        )
    )
    env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)
    rendered = env.get_template("master_data_workspace.html").render(
        request=SimpleNamespace(query_params={}),
        models=[],
        categories=[SimpleNamespace(id=1, name="فئة اختبار", code="C-100")],
        types=[
            SimpleNamespace(
                id=2,
                name="نوع اختبار",
                category_id=1,
                measurement_unit="hours",
                theoretical_quantity=10,
            )
        ],
        brands=[],
        spec_definitions=[],
        tire_master_data={},
    )
    assert 'data-code="C-100"' in rendered
    assert 'data-measurement-unit="hours"' in rendered
    assert 'data-theoretical-quantity="10"' in rendered


def test_ref_panel_accepts_dataset_as_extra_argument():
    template = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(
        encoding="utf-8"
    )
    assert "function refPanel(kind,id=null,name='',extra={})" in template
    assert "extra.code" in template
    assert "extra.categoryId" in template
    assert "extra.measurementUnit" in template
    assert "extra.theoreticalQuantity" in template
    script = Path("static/js/master-data-tree.js").read_text(encoding="utf-8")
    assert "refPanel(kind, id, node.dataset.name || '', node.dataset)" in script


def test_tree_editor_passes_dataset_and_category_attribute_is_primary_source():
    script = Path("static/js/master-data-tree.js").read_text(encoding="utf-8")
    assert "refPanel(kind, id, node.dataset.name || '', node.dataset)" in script
    assert "const attr = String(typeNode.dataset.categoryId || typeNode.dataset.category || '');" in script
    assert "return attr || typeCategoryMap.get(id) || '';" in script
