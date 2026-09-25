import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types import services
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType
from app.modules.equipment_types.schemas import EquipmentBrandCreate, EquipmentBrandUpdate, EquipmentCategoryCreate, EquipmentCategoryUpdate, EquipmentModelCreate, EquipmentTypeCreate, EquipmentTypeUpdate

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)

def setup_db():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine); return Session()

def test_category_edit_and_delete_protection():
    db=setup_db()
    try:
        category=services.create_category(db,EquipmentCategoryCreate(name="مركبات اختبار",code="test-vehicles"))
        updated=services.update_category(db,category,EquipmentCategoryUpdate(name="مركبات محدثة",code="test-vehicles-2"))
        assert updated.name=="مركبات محدثة"; assert updated.code=="test-vehicles-2"
        equipment_type=services.create_type(db,EquipmentTypeCreate(name="نوع مرجعي",measurement_unit="km",category_id=updated.id))
        with pytest.raises(ValueError,match="مرتبطة بأنواع"): services.delete_category(db,updated)
        assert db.get(EquipmentType,equipment_type.id).category_id==updated.id
    finally: db.close()

def test_brand_edit_and_deactivation_prevents_new_model_assignment():
    db=setup_db()
    try:
        category=EquipmentCategory(name="فئة العلامات",code="brands-test"); db.add(category); db.flush()
        equipment_type=EquipmentType(name="نوع العلامات",measurement_unit="km",category_id=category.id); brand=EquipmentBrand(name="Brand A",is_active=True)
        db.add_all([equipment_type,brand]); db.commit()
        services.update_brand(db,brand,EquipmentBrandUpdate(name="Brand A Updated")); services.set_brand_active(db,brand,False)
        assert brand.name=="Brand A Updated"; assert not brand.is_active
        with pytest.raises(ValueError,match="غير نشطة"):
            services.create_model(db,EquipmentModelCreate(name="Model A",equipment_type_id=equipment_type.id,brand_id=brand.id))
    finally: db.close()

def test_type_edit_respects_frozen_state():
    db=setup_db()
    try:
        category=EquipmentCategory(name="فئة الأنواع",code="types-test",is_system=False); db.add(category); db.flush()
        equipment_type=EquipmentType(name="نوع قابل للتعديل",measurement_unit="km",category_id=category.id); db.add(equipment_type); db.commit()
        services.update_type(db,equipment_type,EquipmentTypeUpdate(name="نوع محدث",measurement_unit="km",category_id=category.id,theoretical_quantity=8))
        assert equipment_type.name=="نوع محدث"; assert equipment_type.theoretical_quantity==8
        services.set_type_frozen(db,equipment_type,True)
        with pytest.raises(ValueError,match="مجمد"): services.update_type(db,equipment_type,EquipmentTypeUpdate(name="ممنوع",measurement_unit="km",category_id=category.id))
    finally: db.close()

def test_type_measurement_unit_change_is_blocked_when_equipment_exists():
    db=setup_db()
    try:
        category=EquipmentCategory(name="فئة القياس",code="measurement-test",is_system=False); db.add(category); db.flush()
        equipment_type=EquipmentType(name="نوع مرتبط",measurement_unit="km",category_id=category.id); db.add(equipment_type); db.flush()
        model=EquipmentModel(name="طراز مرتبط",equipment_type_id=equipment_type.id); db.add(model); db.flush()
        equipment=Equipment(asset_code="REF-001",equipment_type_id=equipment_type.id,equipment_model_id=model.id); db.add(equipment); db.commit()
        with pytest.raises(ValueError,match="وحدة القياس"):
            services.update_type(db,equipment_type,EquipmentTypeUpdate(name=equipment_type.name,measurement_unit="hours",category_id=category.id))
    finally: db.close()
