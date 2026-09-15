import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types import services
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType
from app.modules.equipment_types.schemas import EquipmentModelCreate, TirePositionInput
from app.modules.tires.models import Tire, TireModelSize, TireMovement, TirePosition

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def newdb():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session()


def base(db):
    category = EquipmentCategory(name="tire-cat", code="TIRE", is_system=True)
    brand = EquipmentBrand(name="tire-brand", is_active=True)
    db.add_all([category, brand])
    db.flush()
    equipment_type = EquipmentType(name="tire-type", measurement_unit="km", category_id=category.id)
    db.add(equipment_type)
    db.flush()
    return equipment_type, brand


def tire_data(equipment_type, brand, *, name="tire-model", positions=None, sizes=None):
    positions = positions or []
    sizes = sizes or []
    return EquipmentModelCreate(
        name=name,
        equipment_type_id=equipment_type.id,
        brand_id=brand.id,
        has_tires=True,
        tire_positions_required=len(positions),
        axle_count=1,
        tire_size=sizes[0] if sizes else None,
        positions=positions,
        sizes=sizes,
    )


def position(side="left", position_type="single", axle=1, description=None):
    return TirePositionInput(
        axle_number=axle,
        side=side,
        position_type=position_type,
        description=description,
    )


def model_positions(db, model_id):
    return db.query(TirePosition).filter_by(equipment_model_id=model_id).order_by(TirePosition.id).all()


def test_create_persists_model_owned_positions_and_sizes():
    db = newdb()
    equipment_type, brand = base(db)
    model = services.create_model(
        db,
        tire_data(
            equipment_type,
            brand,
            positions=[position("left"), position("right")],
            sizes=["235/75R15", "245/70R16"],
        ),
    )

    rows = model_positions(db, model.id)
    sizes = [row.size for row in db.query(TireModelSize).filter_by(equipment_model_id=model.id).order_by(TireModelSize.id)]
    assert len(rows) == 2
    assert {row.side for row in rows} == {"left", "right"}
    assert sizes == ["235/75R15", "245/70R16"]
    db.close()


def test_create_rejects_position_count_mismatch():
    db = newdb()
    equipment_type, brand = base(db)
    data = tire_data(equipment_type, brand, positions=[position("left")], sizes=["235/75R15"])
    data.tire_positions_required = 2

    with pytest.raises(ValueError, match="بالضبط"):
        services.create_model(db, data)
    db.rollback()
    assert db.query(EquipmentModel).count() == 0
    db.close()


def test_create_rejects_duplicate_positions():
    db = newdb()
    equipment_type, brand = base(db)
    data = tire_data(
        equipment_type,
        brand,
        positions=[position("left"), position("left")],
        sizes=["235/75R15"],
    )

    with pytest.raises(ValueError, match="مكررة"):
        services.create_model(db, data)
    db.rollback()
    assert db.query(EquipmentModel).count() == 0
    db.close()


def test_update_replaces_model_owned_sizes_and_positions():
    db = newdb()
    equipment_type, brand = base(db)
    model = services.create_model(
        db,
        tire_data(equipment_type, brand, positions=[position("left"), position("right")], sizes=["235/75R15", "245/70R16"]),
    )
    old_positions = model_positions(db, model.id)
    updated = tire_data(equipment_type, brand, name=model.name, positions=[position("left", "inner"), position("right", "outer")], sizes=["265/70R16"])
    updated.positions[0].id = old_positions[0].id
    updated.positions[1].id = old_positions[1].id

    services.update_model(db, model, updated)

    rows = model_positions(db, model.id)
    sizes = [row.size for row in db.query(TireModelSize).filter_by(equipment_model_id=model.id)]
    assert {(row.side, row.position_type) for row in rows} == {("left", "inner"), ("right", "outer")}
    assert sizes == ["265/70R16"]
    db.close()


def test_historical_position_cannot_be_deleted_by_model_update():
    db = newdb()
    equipment_type, brand = base(db)
    model = services.create_model(
        db,
        tire_data(equipment_type, brand, positions=[position("left"), position("right")], sizes=["235/75R15"]),
    )
    rows = model_positions(db, model.id)
    tire = Tire(serial_number="HIST-001", size="235/75R15")
    db.add(tire)
    db.flush()
    from datetime import date, datetime
    db.add(
        TireMovement(
            tire_id=tire.id,
            movement_date=date.today(),
            movement_datetime=datetime.now(),
            movement_type="install",
            position_id=rows[0].id,
        )
    )
    db.commit()

    updated = tire_data(equipment_type, brand, name=model.name, positions=[position("right")], sizes=["235/75R15"])
    updated.positions[0].id = rows[1].id
    updated.tire_positions_required = 1

    with pytest.raises(ValueError, match="استُخدم"):
        services.update_model(db, model, updated)
    db.rollback()
    assert db.query(TirePosition).filter_by(id=rows[0].id).count() == 1
    db.close()
