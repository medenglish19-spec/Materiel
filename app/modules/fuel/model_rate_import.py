"""Excel template and validation for fuel consumption rates by model."""

from collections import Counter
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.orm import Session, joinedload

from app.modules.equipment_types.models import EquipmentModel
from app.modules.fuel.models import FuelModelConsumptionRate


MODEL_RATE_HEADERS = ("الطراز", "نوع الوقود", "معدل الاستهلاك", "وحدة القياس")
FUEL_TYPE_OPTIONS = ("ديزل", "بنزين", "غاز بترولي مسال", "غاز طبيعي")
CONSUMPTION_UNIT_OPTIONS = ("لتر/100 كم", "لتر/ساعة")


def list_models(db: Session) -> list[EquipmentModel]:
    return (
        db.query(EquipmentModel)
        .options(joinedload(EquipmentModel.brand), joinedload(EquipmentModel.equipment_type))
        .order_by(EquipmentModel.name, EquipmentModel.id)
        .all()
    )


def model_label(model: EquipmentModel) -> str:
    brand = model.brand.name if model.brand else "بدون علامة تجارية"
    return f"{brand} · {model.name}"


def template_model_labels(models: list[EquipmentModel]) -> dict[str, EquipmentModel]:
    name_counts = Counter(model.name.strip().casefold() for model in models if model.name)
    labels = {}
    for model in models:
        name = model.name.strip()
        label = f"{name} · رقم {model.id}" if name_counts[name.casefold()] > 1 else name
        labels[label] = model
    return labels


def build_model_rate_template(models: list[EquipmentModel]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "معدلات الاستهلاك"
    sheet.append(MODEL_RATE_HEADERS)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = "A1:D501"
    widths = (34, 22, 20, 20)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width

    model_names = sorted(template_model_labels(models))
    lists = workbook.create_sheet("قوائم")
    lists.sheet_state = "hidden"
    for row, value in enumerate(model_names, start=1):
        lists.cell(row=row, column=1, value=value)
    for row, value in enumerate(FUEL_TYPE_OPTIONS, start=1):
        lists.cell(row=row, column=2, value=value)
    for row, value in enumerate(CONSUMPTION_UNIT_OPTIONS, start=1):
        lists.cell(row=row, column=3, value=value)

    if model_names:
        workbook.defined_names.add(DefinedName(
            "FuelRateModels", attr_text=f"'قوائم'!$A$1:$A${len(model_names)}"
        ))
    workbook.defined_names.add(DefinedName("FuelTypes", attr_text=f"'قوائم'!$B$1:$B${len(FUEL_TYPE_OPTIONS)}"))
    workbook.defined_names.add(DefinedName("FuelRateUnits", attr_text=f"'قوائم'!$C$1:$C${len(CONSUMPTION_UNIT_OPTIONS)}"))

    fuel_validation = DataValidation(type="list", formula1="=FuelTypes", allow_blank=False)
    unit_validation = DataValidation(type="list", formula1="=FuelRateUnits", allow_blank=False)
    validations = [(fuel_validation, "B2:B501"), (unit_validation, "D2:D501")]
    if model_names:
        validations.insert(0, (DataValidation(type="list", formula1="=FuelRateModels", allow_blank=False), "A2:A501"))
    for validation, target in validations:
        sheet.add_data_validation(validation)
        validation.add(target)
    sheet["C2"].number_format = "0.00"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def parse_model_rate_workbook(content: bytes, models: list[EquipmentModel]) -> list[dict]:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("تعذر قراءة الملف؛ استخدم قالب Excel بصيغة .xlsx.") from exc
    if "معدلات الاستهلاك" not in workbook.sheetnames:
        raise ValueError("يجب أن يحتوي الملف ورقة «معدلات الاستهلاك».")
    sheet = workbook["معدلات الاستهلاك"]
    headers = tuple(str(cell or "").strip() for cell in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ()))
    if headers != MODEL_RATE_HEADERS:
        raise ValueError("رأس الجدول غير مطابق لقالب معدلات استهلاك الوقود.")

    model_map = {label.strip().casefold(): model for label, model in template_model_labels(models).items()}
    rows: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for row_number, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        values = tuple(values[:4])
        if not any(value not in (None, "") for value in values):
            continue
        model_name, fuel_type, raw_rate, unit = (str(value or "").strip() for value in values)
        model = model_map.get(model_name.casefold())
        if model is None:
            raise ValueError(f"الطراز في الصف {row_number} غير موجود في بيانات البرنامج. اختره من قائمة القالب.")
        if fuel_type not in FUEL_TYPE_OPTIONS:
            raise ValueError(f"نوع الوقود في الصف {row_number} غير مدرج في القائمة المعتمدة.")
        if unit not in CONSUMPTION_UNIT_OPTIONS:
            raise ValueError(f"وحدة القياس في الصف {row_number} غير مدرجة في القائمة المعتمدة.")
        try:
            rate = Decimal(raw_rate)
        except (InvalidOperation, ValueError):
            raise ValueError(f"معدل الاستهلاك في الصف {row_number} يجب أن يكون رقمًا.") from None
        if not rate.is_finite() or rate <= 0:
            raise ValueError(f"معدل الاستهلاك في الصف {row_number} يجب أن يكون أكبر من صفر.")
        key = (model.id, fuel_type)
        if key in seen:
            raise ValueError(f"يوجد تكرار للطراز ونوع الوقود في الصف {row_number}.")
        seen.add(key)
        rows.append({
            "equipment_model_id": model.id,
            "fuel_type": fuel_type,
            "consumption_rate": rate,
            "measurement_unit": unit,
        })
    if not rows:
        raise ValueError("لا يحتوي الملف على معدلات استهلاك لإدخالها.")
    return rows


def save_model_rates(db: Session, rows: list[dict]) -> int:
    for row in rows:
        existing = db.query(FuelModelConsumptionRate).filter_by(
            equipment_model_id=row["equipment_model_id"], fuel_type=row["fuel_type"]
        ).one_or_none()
        if existing:
            existing.consumption_rate = row["consumption_rate"]
            existing.measurement_unit = row["measurement_unit"]
        else:
            db.add(FuelModelConsumptionRate(**row))
    db.commit()
    return len(rows)
