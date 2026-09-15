import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database.base import Base
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType
from app.modules.equipment_types.schemas import EquipmentModelCreate
from app.modules.equipment_types import services
from app.modules.tires.models import Tire, TireMovement, TireModelSize, TirePosition

engine=create_engine("sqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool)
Session=sessionmaker(bind=engine)

def db_new():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine); return Session()

def base(db):
    cat=EquipmentCategory(name="اختبار",code="TEST",is_system=True); brand=EquipmentBrand(name="اختبار",is_active=True); db.add_all([cat,brand]); db.flush(); typ=EquipmentType(name="مركبات اختبار",measurement_unit="km",category_id=cat.id); db.add(typ); db.flush(); return typ,brand

def data(typ,brand,positions, sizes=None, tire_size="315/80R22.5"):
    return EquipmentModelCreate(name="طراز اختبار",equipment_type_id=typ.id,brand_id=brand.id,has_tires=True,tire_positions_required=len(positions),tire_size=tire_size,positions=positions,sizes=sizes or [],has_batteries=False)

def pos(axle=1,side="left",kind="single",id=None): return {"id":id,"axle_number":axle,"side":side,"position_type":kind,"description":""}

def test_create_rejects_wrong_position_count_without_model():
    db=db_new(); typ,brand=base(db)
    try:
        d=data(typ,brand,[pos(1)],sizes=[])
        d.tire_positions_required=2
        with pytest.raises(ValueError,match="بالضبط") : services.create_model(db,d)
        assert db.query(EquipmentModel).count()==0
        assert db.query(TirePosition).count()==0
    finally: db.close()

def test_create_matching_positions_is_atomic_and_persists_sizes():
    db=db_new(); typ,brand=base(db)
    try:
        d=data(typ,brand,[pos(1,"left"),pos(1,"right")],sizes=["12R22.5"])
        model=services.create_model(db,d)
        assert db.query(TirePosition).filter_by(equipment_model_id=model.id).count()==2
        assert [x.size for x in db.query(TireModelSize).filter_by(equipment_model_id=model.id).all()]==["12R22.5"]
    finally: db.close()

def test_create_without_default_or_additional_size_is_rejected():
    db=db_new(); typ,brand=base(db)
    try:
        d=data(typ,brand,[pos(1)],sizes=[],tire_size="")
        with pytest.raises(ValueError,match="مقاس") : services.create_model(db,d)
        assert db.query(EquipmentModel).count()==0
    finally: db.close()

def test_update_cannot_delete_position_used_by_movement():
    db=db_new(); typ,brand=base(db)
    try:
        model=services.create_model(db,data(typ,brand,[pos(1)]))
        position=db.query(TirePosition).filter_by(equipment_model_id=model.id).one()
        tire=Tire(serial_number="TEST-TIRE-1",size="315/80R22.5",expiry_date=date(2030,1,1)); db.add(tire); db.flush()
        from app.modules.equipment.models import Equipment
        equipment=Equipment(asset_code="TEST-EQ-1",equipment_type_id=typ.id,equipment_model_id=model.id); db.add(equipment); db.flush()
        db.add(TireMovement(tire_id=tire.id,movement_date=date(2026,9,1),movement_datetime=datetime(2026,9,1,10),movement_type="install",equipment_id=equipment.id,position_id=position.id)); db.commit()
        d=data(typ,brand,[]) ; d.name=model.name; d.tire_positions_required=0
        with pytest.raises(ValueError,match="حافظ على التاريخ"): services.update_model(db,model,d)
        db.rollback(); db.refresh(model); assert db.query(TirePosition).filter_by(id=position.id).first() is not None
    finally: db.close()

def test_non_tire_model_rejects_submitted_tire_configuration():
    db=db_new(); typ,brand=base(db)
    try:
        d=EquipmentModelCreate(name="بدون إطارات",equipment_type_id=typ.id,brand_id=brand.id,has_tires=False,positions=[pos(1)],sizes=[])
        with pytest.raises(ValueError,match="غير مزود") : services.create_model(db,d)
        assert db.query(EquipmentModel).count()==0
    finally: db.close()

def test_removed_tire_configuration_routes_are_not_registered():
    from app.modules.tires.router import router
    paths={route.path for route in router.routes}
    assert "/tires/positions" not in paths
    assert "/tires/models/{model_id}/configuration" not in paths
