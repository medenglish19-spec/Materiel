# Custom technical properties regression coverage
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database.base import Base
from app.modules.users.models import User
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentBrand,EquipmentCategory,EquipmentModel,EquipmentModelSpecValue,EquipmentType
# Register all project model modules so SQLAlchemy can resolve cross-module relationships in the isolated test schema.
from app.modules.batteries import models as _batteries_models
from app.modules.faults_repairs import models as _faults_repairs_models
from app.modules.fuel import models as _fuel_models
from app.modules.maintenance import models as _maintenance_models
from app.modules.meter_readings import models as _meter_readings_models
from app.modules.missions import models as _missions_models
from app.modules.tires import models as _tires_models
from app.modules.equipment_types.schemas import EquipmentModelCreate,SpecDefinitionCreate,SpecValueInput
from app.modules.equipment_types import services
# Load the full application model registry before Base.metadata.create_all().
# services imports tires, whose relationships reference equipment and other cross-module models.
from web.main import app as _app
engine=create_engine("sqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool);Session=sessionmaker(bind=engine)
def newdb():
    # Register cross-module audit FK target before creating the isolated test schema.
    _ = (User, Equipment)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session()
def base(db):
 c=EquipmentCategory(name="spec-cat",code="SPEC",is_system=True);b=EquipmentBrand(name="spec-brand",is_active=True);db.add_all([c,b]);db.flush();t=EquipmentType(name="spec-type",measurement_unit="km",category_id=c.id);db.add(t);db.flush();return t,b
def data(t,b,specs=None,name="spec-model"):return EquipmentModelCreate(name=name,equipment_type_id=t.id,brand_id=b.id,specs=specs or [])
def test_number_invalid():
 db=newdb();t,b=base(db);d=services.create_spec_definition(db,SpecDefinitionCreate(name="weight",data_type="number"));
 with pytest.raises(ValueError,match="رقمًا"):services.create_model(db,data(t,b,[SpecValueInput(definition_id=d.id,value="abc")]));db.rollback();assert db.query(EquipmentModel).count()==0;db.close()
def test_select_invalid():
 db=newdb();t,b=base(db);d=services.create_spec_definition(db,SpecDefinitionCreate(name="gear",data_type="select",options="يدوي,أوتوماتيك"));
 with pytest.raises(ValueError,match="إحدى"):services.create_model(db,data(t,b,[SpecValueInput(definition_id=d.id,value="CVT")]));db.rollback();db.close()
def test_empty_optional():
 db=newdb();t,b=base(db);d=services.create_spec_definition(db,SpecDefinitionCreate(name="load",data_type="number"));m=services.create_model(db,data(t,b,[SpecValueInput(definition_id=d.id,value=" ")]));assert db.query(EquipmentModelSpecValue).filter_by(equipment_model_id=m.id).count()==0;db.close()
def test_delete_cascade():
 db=newdb();t,b=base(db);d=services.create_spec_definition(db,SpecDefinitionCreate(name="fuel"));m1=services.create_model(db,data(t,b,[SpecValueInput(definition_id=d.id,value="ديزل")],"m1"));m2=services.create_model(db,data(t,b,[SpecValueInput(definition_id=d.id,value="بنزين")],"m2"));services.delete_spec_definition(db,d.id);assert db.query(EquipmentModelSpecValue).count()==0;assert db.query(EquipmentModel).filter(EquipmentModel.id.in_([m1.id,m2.id])).count()==2;db.close()
def test_update_same_row():
 db=newdb();t,b=base(db);d=services.create_spec_definition(db,SpecDefinitionCreate(name="weight",data_type="number"));m=services.create_model(db,data(t,b,[SpecValueInput(definition_id=d.id,value="100")]));r=db.query(EquipmentModelSpecValue).one();rid=r.id;services.update_model(db,m,data(t,b,[SpecValueInput(definition_id=d.id,value="125")]));r=db.query(EquipmentModelSpecValue).one();assert r.id==rid and r.value=="125";db.close()
def test_missing_definition():
 db=newdb();t,b=base(db);
 with pytest.raises(ValueError,match="لم تعد معرّفة"):services.create_model(db,data(t,b,[SpecValueInput(definition_id=99999,value="x")]));db.rollback();assert db.query(EquipmentModel).count()==0;db.close()
def test_library_property_can_be_selected_even_when_applicability_differs():
 db=newdb();t,b=base(db);other=EquipmentCategory(name="other-cat",code="OTHER",is_system=True);db.add(other);db.flush()
 d=services.create_spec_definition(db,SpecDefinitionCreate(name="payload",category_id=other.id))
 m=services.create_model(db,data(t,b,[SpecValueInput(definition_id=d.id,value="250")]))
 assert db.query(EquipmentModelSpecValue).filter_by(equipment_model_id=m.id,spec_definition_id=d.id).one().value=="250"
 db.close()
