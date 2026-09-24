"""repair and complete Master Data technical taxonomy

Revision ID: d9f4a7c1e2b3
Revises: c8b492d2cb2f
"""

from alembic import op
import sqlalchemy as sa

revision = "d9f4a7c1e2b3"
down_revision = "c8b492d2cb2f"
branch_labels = None
depends_on = None

TAXONOMY = [
    ("العربات", "vehicles", 10, [
        ("سيارات ركوب", "km"), ("سيارات نفعية", "km"), ("سيارات دفع رباعي", "km"),
        ("شاحنات خفيفة", "km"), ("شاحنات متوسطة", "km"), ("شاحنات ثقيلة", "km"),
        ("جرارات", "hours"), ("حافلات", "km"), ("حافلات صغيرة", "km"),
        ("مقطورات وأنصاف مقطورات", "km"), ("مركبات خاصة", "km"),
    ]),
    ("معدات المناولة والرفع", "handling_lifting", 20, [
        ("رافعات شوكية", "hours"), ("رافعات متنقلة", "hours"), ("رافعات ثابتة", "hours"),
        ("منصات رفع", "hours"), ("معدات سحب وجر", "hours"),
    ]),
    ("معدات الأشغال والهندسة", "construction_engineering", 30, [
        ("حفارات", "hours"), ("جرافات", "hours"), ("لوادر", "hours"), ("ممهدات", "hours"),
        ("مداحل", "hours"), ("آلات حفر وضغط", "hours"), ("معدات إنشاء الطرق", "hours"),
    ]),
    ("معدات الطاقة", "power", 40, [
        ("مولدات كهربائية", "hours"), ("ضواغط", "hours"), ("وحدات طاقة", "hours"),
        ("معدات توزيع الطاقة", "hours"),
    ]),
    ("المعدات الزراعية", "agriculture", 50, [
        ("جرارات زراعية", "hours"), ("حصادات", "hours"), ("آلات حرث", "hours"),
        ("آلات رش", "hours"), ("معدات زراعية مسحوبة", "hours"),
    ]),
    ("المعدات المتخصصة", "specialized", 60, [
        ("معدات إطفاء", "hours"), ("معدات إنقاذ", "hours"), ("معدات ورش", "hours"),
        ("معدات اتصالات", "hours"), ("معدات ميدانية", "hours"), ("معدات خدمات خاصة", "hours"),
    ]),
]

SPECS = [
    ("الصانع","manufacturer","التعريف الفني","text",None,1),
    ("الطراز","model","التعريف الفني","text",None,2),
    ("الجيل","generation","التعريف الفني","text",None,3),
    ("سنة الصنع","model_year","التعريف الفني","number","سنة",4),
    ("بلد الصنع","country_of_origin","التعريف الفني","text",None,5),
    ("نوع الهيكل","body_type","التعريف الفني","select","بيك أب,سيدان,دفع رباعي,شاحنة,حافلة,خاص",6),
    ("نوع المحرك","engine_type","المحرك / مصدر الطاقة","select","بنزين,ديزل,كهربائي,هجين",10),
    ("عدد الأسطوانات","cylinder_count","المحرك / مصدر الطاقة","number","أسطوانة",11),
    ("سعة المحرك","engine_displacement","المحرك / مصدر الطاقة","number","سم³",12),
    ("القدرة القصوى","max_power","المحرك / مصدر الطاقة","number","kW",13),
    ("عزم الدوران الأقصى","max_torque","المحرك / مصدر الطاقة","number","Nm",14),
    ("نظام الحقن","injection_system","المحرك / مصدر الطاقة","text",None,15),
    ("نظام التبريد","cooling_system","المحرك / مصدر الطاقة","select","سائل,هواء",16),
    ("شاحن توربيني","turbocharged","المحرك / مصدر الطاقة","select","نعم,لا",17),
    ("نوع ناقل الحركة","transmission_type","الحركة / ناقل الحركة","select","يدوي,أوتوماتيكي,نصف أوتوماتيكي,CVT",20),
    ("عدد سرعات ناقل الحركة","gear_count","الحركة / ناقل الحركة","number","سرعة",21),
    ("نظام الدفع","drive_system","الحركة / ناقل الحركة","select","2x4,4x2,4x4,6x4,6x6,8x8",22),
    ("علبة التحويل","transfer_case","الحركة / ناقل الحركة","text",None,23),
    ("نسبة التخفيض","reduction_ratio","الحركة / ناقل الحركة","text",None,24),
    ("الطول الكلي","overall_length","الأبعاد والأوزان","number","mm",30),
    ("العرض الكلي","overall_width","الأبعاد والأوزان","number","mm",31),
    ("الارتفاع الكلي","overall_height","الأبعاد والأوزان","number","mm",32),
    ("قاعدة العجلات","wheelbase","الأبعاد والأوزان","number","mm",33),
    ("الوزن الفارغ","curb_weight","الأبعاد والأوزان","number","kg",34),
    ("الوزن الإجمالي المسموح","gross_vehicle_weight","الأبعاد والأوزان","number","kg",35),
    ("الحمولة الصافية","payload","الأبعاد والأوزان","number","kg",36),
    ("جهد النظام الكهربائي","electrical_voltage","الكهرباء","number","V",40),
    ("سعة المولد","alternator_capacity","الكهرباء","number","A",41),
    ("عدد البطاريات","battery_count","الكهرباء","number","بطارية",42),
    ("سعة البطارية","battery_capacity","الكهرباء","number","Ah",43),
    ("سعة خزان الوقود","fuel_tank_capacity","السوائل والسعات","number","L",50),
    ("زيت المحرك","engine_oil_capacity","السوائل والسعات","number","L",51),
    ("زيت ناقل الحركة","transmission_oil_capacity","السوائل والسعات","number","L",52),
    ("سائل التبريد","coolant_capacity","السوائل والسعات","number","L",53),
    ("سائل الفرامل","brake_fluid_capacity","السوائل والسعات","number","L",54),
    ("مقاس الإطار","tire_size","الإطارات والعجلات","text",None,60),
    ("عدد المحاور","axle_count","الإطارات والعجلات","number","محور",61),
    ("ضغط الإطار","tire_pressure","الإطارات والعجلات","number","bar",62),
    ("نوع الإطار","tire_type","الإطارات والعجلات","select","صيفي,شتوي,كل التضاريس,طريق وعرة",63),
    ("السرعة القصوى","max_speed","الأداء التشغيلي","number","km/h",70),
    ("مدى التشغيل","operating_range","الأداء التشغيلي","number","km",71),
    ("استهلاك الوقود","fuel_consumption","الأداء التشغيلي","number","L/100km",72),
    ("قابلية التسلق","gradeability","الأداء التشغيلي","number","%",73),
    ("نصف قطر الدوران","turning_radius","الأداء التشغيلي","number","m",74),
    ("نوع العداد الرئيسي","primary_meter_type","العدادات / الأجهزة","select","عداد مسافة,عداد ساعات",80),
    ("فترة الصيانة الدورية","service_interval","الصيانة","number","km/ساعة",90),
    ("الصيانة الأولى","first_service_interval","الصيانة","number","km/ساعة",91),
    ("فترة تغيير زيت المحرك","engine_oil_service_interval","الصيانة","number","km/ساعة",92),
    ("فترة تغيير المرشحات","filter_service_interval","الصيانة","number","km/ساعة",93),
    ("نقاط التشحيم","lubrication_points","الصيانة","number","نقطة",94),
    ("درجة حرارة التشغيل","operating_temperature","ظروف التشغيل","text",None,100),
    ("الارتفاع التشغيلي الأقصى","maximum_operating_altitude","ظروف التشغيل","number","m",101),
    ("معيار الانبعاثات","emission_standard","المعايير / الامتثال","text",None,110),
]

OPTIONS = {
    "نوع الهيكل":"بيك أب,سيدان,دفع رباعي,شاحنة,حافلة,خاص",
    "نوع المحرك":"بنزين,ديزل,كهربائي,هجين",
    "نظام التبريد":"سائل,هواء",
    "شاحن توربيني":"نعم,لا",
    "نوع ناقل الحركة":"يدوي,أوتوماتيكي,نصف أوتوماتيكي,CVT",
    "نظام الدفع":"2x4,4x2,4x4,6x4,6x6,8x8",
    "نوع الإطار":"صيفي,شتوي,كل التضاريس,طريق وعرة",
    "نوع العداد الرئيسي":"عداد مسافة,عداد ساعات",
}

def upgrade():
    bind = op.get_bind()
    category_ids = {}
    for name, code, order, type_rows in TAXONOMY:
        row = bind.execute(sa.text("SELECT id FROM equipment_categories WHERE code=:code"), {"code": code}).first()
        if row:
            category_id = row[0]
            bind.execute(sa.text(
                "UPDATE equipment_categories SET name=:name, sort_order=:sort_order, is_system=1 WHERE id=:id"
            ), {"name": name, "sort_order": order, "id": category_id})
        else:
            category_id = bind.execute(sa.text(
                "INSERT INTO equipment_categories (name,code,sort_order,is_system,created_at,updated_at) "
                "VALUES (:name,:code,:sort_order,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING id"
            ), {"name": name, "code": code, "sort_order": order}).scalar_one()
        category_ids[code] = category_id
        for type_name, unit in type_rows:
            row = bind.execute(sa.text(
                "SELECT id FROM equipment_types WHERE name=:name LIMIT 1"
            ), {"name": type_name}).first()
            if row:
                bind.execute(sa.text(
                    "UPDATE equipment_types SET category_id=:category, measurement_unit=:unit "
                    "WHERE id=:id"
                ), {"category": category_id, "unit": unit, "id": row[0]})
            else:
                bind.execute(sa.text(
                    "INSERT INTO equipment_types "
                    "(name,measurement_unit,theoretical_quantity,category_id,is_frozen,created_at,updated_at) "
                    "VALUES (:name,:unit,NULL,:category,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), {"name": type_name, "unit": unit, "category": category_id})

    vehicle_category_id = category_ids["vehicles"]
    for name, code, group_name, data_type, unit, sort_order in SPECS:
        exists = bind.execute(sa.text(
            "SELECT id FROM equipment_model_spec_definitions WHERE code=:code OR name=:name LIMIT 1"
        ), {"code": code, "name": name}).first()
        if exists:
            continue
        bind.execute(sa.text(
            "INSERT INTO equipment_model_spec_definitions "
            "(name,code,data_type,unit,options,sort_order,group_name,group_sort_order,"
            "equipment_type_id,category_id,created_at,updated_at) "
            "VALUES (:name,:code,:dtype,:unit,:options,:sort,:group,:group_sort,NULL,:category,"
            "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        ), {
            "name":name, "code":code, "dtype":data_type, "unit":unit,
            "options":OPTIONS.get(name), "sort":sort_order, "group":group_name,
            "group_sort":sort_order // 10, "category":vehicle_category_id,
        })

def downgrade():
    pass
