"""make technical specifications type-specific

Revision ID: 9c4d7e2a1b6f
Revises: f7b8c9d0e1f2
"""

from alembic import op
import sqlalchemy as sa

revision = "9c4d7e2a1b6f"
down_revision = "f7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS equipment_type_spec_definitions (
            equipment_type_id INTEGER NOT NULL,
            spec_definition_id INTEGER NOT NULL,
            PRIMARY KEY (equipment_type_id, spec_definition_id),
            FOREIGN KEY (equipment_type_id) REFERENCES equipment_types(id) ON DELETE CASCADE,
            FOREIGN KEY (spec_definition_id) REFERENCES equipment_model_spec_definitions(id) ON DELETE CASCADE
        )
    """))
    bind.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_equipment_type_spec_definitions_spec
        ON equipment_type_spec_definitions(spec_definition_id)
    """))

    def type_id(name):
        row = bind.execute(sa.text("SELECT id FROM equipment_types WHERE name=:name"), {"name": name}).fetchone()
        return row[0] if row else None

    def spec_id(code, name, group_name, data_type="text", unit=None, options=None, group_sort=0, sort_order=0):
        row = bind.execute(sa.text(
            "SELECT id FROM equipment_model_spec_definitions WHERE code=:code OR name=:name"
        ), {"code": code, "name": name}).fetchone()
        if row:
            return row[0]
        return bind.execute(sa.text("""
            INSERT INTO equipment_model_spec_definitions
            (name,code,data_type,unit,options,sort_order,group_name,group_sort_order,
             equipment_type_id,category_id,created_at,updated_at)
            VALUES (:name,:code,:dtype,:unit,:options,:sort,:group,:gsort,NULL,NULL,
                    CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
            RETURNING id
        """), {
            "name": name, "code": code, "dtype": data_type, "unit": unit,
            "options": options, "sort": sort_order, "group": group_name, "gsort": group_sort,
        }).scalar_one()

    # Existing vehicle dictionary becomes a reusable technical library,
    # but applicability is now decided by explicit type-to-property links.
    all_vehicle_types = [
        "سيارات ركوب", "سيارات نفعية", "سيارات دفع رباعي",
        "شاحنات خفيفة", "شاحنات متوسطة", "شاحنات ثقيلة",
        "جرارات", "حافلات", "مقطورات وأنصاف مقطورات", "مركبات خاصة",
    ]
    vehicle_codes = [
        "manufacturer","model","generation","model_year","country_of_origin","body_type",
        "engine_type","cylinder_count","engine_displacement","max_power","max_torque",
        "injection_system","cooling_system","turbocharged",
        "transmission_type","gear_count","drive_system","transfer_case","reduction_ratio",
        "overall_length","overall_width","overall_height","wheelbase","curb_weight",
        "gross_vehicle_weight","payload","electrical_voltage","alternator_capacity",
        "battery_count","battery_capacity","fuel_tank_capacity","engine_oil_capacity",
        "transmission_oil_capacity","coolant_capacity","brake_fluid_capacity",
        "tire_size","axle_count","tire_pressure","tire_type","max_speed","operating_range",
        "fuel_consumption","gradeability","turning_radius","primary_meter_type",
        "service_interval","first_service_interval","engine_oil_service_interval",
        "filter_service_interval","lubrication_points","operating_temperature",
        "maximum_operating_altitude","emission_standard",
    ]
    vehicle_specs = {}
    for code in vehicle_codes:
        row = bind.execute(sa.text(
            "SELECT id FROM equipment_model_spec_definitions WHERE code=:code"
        ), {"code": code}).fetchone()
        if row:
            vehicle_specs[code] = row[0]

    common_vehicle = {
        "manufacturer","model","generation","model_year","country_of_origin","body_type",
        "engine_type","max_power","max_torque","transmission_type","gear_count",
        "overall_length","overall_width","overall_height","curb_weight",
        "gross_vehicle_weight","electrical_voltage","battery_count","battery_capacity",
        "fuel_tank_capacity","engine_oil_capacity","coolant_capacity","tire_size",
        "axle_count","tire_pressure","tire_type","primary_meter_type",
        "service_interval","first_service_interval","engine_oil_service_interval",
        "filter_service_interval","lubrication_points","operating_temperature",
        "maximum_operating_altitude","emission_standard",
    }
    profiles = {
        "سيارات ركوب": common_vehicle | {"cylinder_count","engine_displacement","injection_system","cooling_system","turbocharged","operating_range","fuel_consumption","max_speed","turning_radius"},
        "سيارات نفعية": common_vehicle | {"cylinder_count","engine_displacement","injection_system","cooling_system","turbocharged","payload","operating_range","fuel_consumption","max_speed","turning_radius","drive_system"},
        "سيارات دفع رباعي": common_vehicle | {"cylinder_count","engine_displacement","injection_system","cooling_system","turbocharged","drive_system","transfer_case","reduction_ratio","operating_range","fuel_consumption","max_speed","gradeability","turning_radius"},
        "شاحنات خفيفة": common_vehicle | {"cylinder_count","engine_displacement","injection_system","cooling_system","turbocharged","drive_system","payload","fuel_consumption","max_speed","gradeability"},
        "شاحنات متوسطة": common_vehicle | {"cylinder_count","engine_displacement","injection_system","cooling_system","turbocharged","drive_system","payload","fuel_consumption","max_speed","gradeability","reduction_ratio"},
        "شاحنات ثقيلة": common_vehicle | {"cylinder_count","engine_displacement","injection_system","cooling_system","turbocharged","drive_system","transfer_case","reduction_ratio","payload","fuel_consumption","max_speed","gradeability"},
        "جرارات": common_vehicle | {"cylinder_count","engine_displacement","injection_system","cooling_system","turbocharged","drive_system","reduction_ratio","gradeability"},
        "حافلات": common_vehicle | {"cylinder_count","engine_displacement","injection_system","cooling_system","turbocharged","drive_system","payload","operating_range","fuel_consumption","max_speed","turning_radius"},
        "مقطورات وأنصاف مقطورات": {"manufacturer","model","generation","model_year","country_of_origin","body_type","overall_length","overall_width","overall_height","curb_weight","gross_vehicle_weight","payload","tire_size","axle_count","tire_pressure","tire_type","primary_meter_type","service_interval","operating_temperature","maximum_operating_altitude","emission_standard"},
        "مركبات خاصة": common_vehicle | {"cylinder_count","engine_displacement","injection_system","cooling_system","turbocharged","drive_system","payload","operating_range","fuel_consumption","max_speed","gradeability","turning_radius"},
    }

    for type_name, codes in profiles.items():
        tid = type_id(type_name)
        if not tid:
            continue
        for code in codes:
            sid = vehicle_specs.get(code)
            if sid:
                bind.execute(sa.text("""
                    INSERT OR IGNORE INTO equipment_type_spec_definitions
                    (equipment_type_id,spec_definition_id) VALUES (:tid,:sid)
                """), {"tid": tid, "sid": sid})

    # Type-specific technical extensions for the remaining library families.
    definitions = [
        ("lift_capacity","قدرة الرفع","الرفع والمناولة","number","kg"),
        ("lift_height","ارتفاع الرفع","الرفع والمناولة","number","mm"),
        ("load_center","مركز الحمولة","الرفع والمناولة","number","mm"),
        ("fork_length","طول الشوكة","الرفع والمناولة","number","mm"),
        ("boom_length","طول الذراع","الرفع والمناولة","number","m"),
        ("max_reach","أقصى مدى وصول","الرفع والمناولة","number","m"),
        ("rated_load","الحمل المقنن","الرفع والمناولة","number","kg"),
        ("platform_height","ارتفاع المنصة","الرفع والمناولة","number","m"),
        ("towing_capacity","قدرة السحب","السحب والجر","number","kg"),
        ("operating_weight","وزن التشغيل","الأبعاد والأوزان","number","kg"),
        ("bucket_capacity","سعة الدلو","الحفر والتحميل","number","m³"),
        ("digging_depth","عمق الحفر","الحفر والتحميل","number","m"),
        ("digging_force","قوة الحفر","الحفر والتحميل","number","kN"),
        ("blade_width","عرض الشفرة","أعمال التربة والطرق","number","m"),
        ("compaction_width","عرض الدمك","أعمال التربة والطرق","number","m"),
        ("compaction_frequency","تردد الاهتزاز","أعمال التربة والطرق","number","Hz"),
        ("electrical_power","القدرة الكهربائية","الكهرباء","number","kVA"),
        ("rated_voltage","الجهد المقنن","الكهرباء","number","V"),
        ("frequency","التردد","الكهرباء","number","Hz"),
        ("phase_count","عدد الأطوار","الكهرباء","number","طور"),
        ("power_factor","معامل القدرة","الكهرباء","number",None),
        ("air_flow","معدل تدفق الهواء","الضواغط","number","m³/min"),
        ("working_pressure","ضغط التشغيل","الضواغط والهيدروليك","number","bar"),
        ("hydraulic_flow","التدفق الهيدروليكي","الهيدروليك","number","L/min"),
        ("hydraulic_pressure","الضغط الهيدروليكي","الهيدروليك","number","bar"),
        ("pto_power","قدرة مأخذ القدرة","الجر والقدرة","number","kW"),
        ("cutting_width","عرض العمل","المعدات الزراعية","number","m"),
        ("hopper_capacity","سعة القادوس","السعة التشغيلية","number","m³"),
        ("tank_capacity","سعة الخزان","السعة التشغيلية","number","L"),
        ("water_flow","معدل تدفق المياه","أنظمة الرش","number","L/min"),
        ("communication_standard","معيار الاتصال","الاتصالات","text",None),
        ("rescue_load","حمولة الإنقاذ","الإنقاذ والطوارئ","number","kg"),
        ("extinguishing_agent_capacity","سعة مادة الإطفاء","الإطفاء","number","L"),
    ]
    ext = {}
    for code,name,group,dtype,unit in definitions:
        ext[code] = spec_id(code,name,group,dtype,unit,group_sort=120,sort_order=120)

    family_profiles = {
        "معدات المناولة والرفع": {
            "رافعات شوكية":{"lift_capacity","lift_height","load_center","fork_length","operating_weight","tire_size","tire_pressure","battery_capacity","electrical_voltage","primary_meter_type","service_interval"},
            "رافعات متنقلة":{"lift_capacity","boom_length","max_reach","rated_load","operating_weight","engine_type","max_power","tire_size","tire_pressure","primary_meter_type","service_interval"},
            "رافعات ثابتة":{"lift_capacity","boom_length","max_reach","rated_load","electrical_voltage","electrical_power","primary_meter_type","service_interval"},
            "منصات رفع":{"platform_height","rated_load","max_reach","operating_weight","electrical_voltage","primary_meter_type","service_interval"},
            "معدات سحب وجر":{"towing_capacity","operating_weight","engine_type","max_power","tire_size","primary_meter_type","service_interval"},
        },
        "معدات الأشغال والهندسة": {
            "حفارات":{"operating_weight","engine_type","max_power","hydraulic_flow","hydraulic_pressure","bucket_capacity","digging_depth","digging_force","max_reach","tire_size","primary_meter_type","service_interval"},
            "جرافات":{"operating_weight","engine_type","max_power","blade_width","towing_capacity","tire_size","primary_meter_type","service_interval"},
            "لوادر":{"operating_weight","engine_type","max_power","bucket_capacity","lift_capacity","tire_size","primary_meter_type","service_interval"},
            "ممهدات":{"operating_weight","engine_type","max_power","blade_width","tire_size","primary_meter_type","service_interval"},
            "مداحل":{"operating_weight","engine_type","max_power","compaction_width","compaction_frequency","tire_size","primary_meter_type","service_interval"},
            "آلات حفر وضغط":{"operating_weight","engine_type","max_power","hydraulic_flow","hydraulic_pressure","digging_depth","digging_force","primary_meter_type","service_interval"},
            "معدات إنشاء الطرق":{"operating_weight","engine_type","max_power","blade_width","compaction_width","compaction_frequency","primary_meter_type","service_interval"},
        },
        "معدات الطاقة": {
            "مولدات كهربائية":{"electrical_power","rated_voltage","frequency","phase_count","power_factor","engine_type","max_power","fuel_tank_capacity","primary_meter_type","service_interval"},
            "ضواغط":{"engine_type","max_power","air_flow","working_pressure","fuel_tank_capacity","primary_meter_type","service_interval"},
            "وحدات طاقة":{"electrical_power","rated_voltage","frequency","phase_count","power_factor","battery_capacity","primary_meter_type","service_interval"},
            "معدات توزيع الطاقة":{"rated_voltage","frequency","phase_count","power_factor","electrical_power","primary_meter_type","service_interval"},
        },
        "المعدات الزراعية": {
            "جرارات زراعية":{"engine_type","cylinder_count","engine_displacement","max_power","max_torque","transmission_type","drive_system","pto_power","towing_capacity","tire_size","primary_meter_type","service_interval"},
            "حصادات":{"engine_type","max_power","hopper_capacity","cutting_width","operating_weight","tire_size","primary_meter_type","service_interval"},
            "آلات حرث":{"engine_type","max_power","cutting_width","towing_capacity","primary_meter_type","service_interval"},
            "آلات رش":{"engine_type","max_power","tank_capacity","water_flow","cutting_width","primary_meter_type","service_interval"},
            "معدات زراعية مسحوبة":{"towing_capacity","tank_capacity","cutting_width","operating_weight","tire_size","primary_meter_type","service_interval"},
        },
        "المعدات المتخصصة": {
            "معدات إطفاء":{"engine_type","max_power","tank_capacity","extinguishing_agent_capacity","rescue_load","tire_size","primary_meter_type","service_interval"},
            "معدات إنقاذ":{"engine_type","max_power","rescue_load","hydraulic_flow","hydraulic_pressure","towing_capacity","primary_meter_type","service_interval"},
            "معدات ورش":{"electrical_power","rated_voltage","working_pressure","hydraulic_flow","hydraulic_pressure","primary_meter_type","service_interval"},
            "معدات اتصالات":{"electrical_voltage","battery_capacity","communication_standard","primary_meter_type","service_interval"},
            "معدات ميدانية":{"engine_type","max_power","towing_capacity","operating_weight","tire_size","primary_meter_type","service_interval"},
            "معدات خدمات خاصة":{"engine_type","max_power","electrical_power","rated_voltage","operating_weight","primary_meter_type","service_interval"},
        },
    }
    category_codes = {
        "معدات المناولة والرفع":"handling_lifting",
        "معدات الأشغال والهندسة":"construction_engineering",
        "معدات الطاقة":"power",
        "المعدات الزراعية":"agriculture",
        "المعدات المتخصصة":"specialized",
    }
    for family, profiles2 in family_profiles.items():
        for type_name, codes in profiles2.items():
            tid = type_id(type_name)
            if not tid:
                continue
            for code in codes:
                sid = ext.get(code) or vehicle_specs.get(code)
                if sid:
                    bind.execute(sa.text("""
                        INSERT OR IGNORE INTO equipment_type_spec_definitions
                        (equipment_type_id,spec_definition_id) VALUES (:tid,:sid)
                    """), {"tid": tid, "sid": sid})


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("DROP TABLE IF EXISTS equipment_type_spec_definitions"))
