"""Excel template and direct importer for model-scoped maintenance operations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
import unicodedata
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.equipment_types.models import EquipmentModel
from app.modules.maintenance.models import (
    MaintenanceModelOperation,
    MaintenanceOperationGroup,
)


GROUP_NO_VALUE = "بدون مجموعة"
MAX_OPERATION_IMPORT_ROWS = 2000
OPERATION_IMPORT_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_CONDITION_AXES = 3
MAX_WARNING_AXES = 3

OPERATION_IMPORT_HEADERS = (
    "العملية",
    "الوصف",
    "المجموعة",
    "قيمة الشرط 1",
    "وحدة الشرط 1",
    "قيمة الشرط 2",
    "وحدة الشرط 2",
    "قيمة الشرط 3",
    "وحدة الشرط 3",
    "قيمة الإنذار 1",
    "وحدة الإنذار 1",
    "قيمة الإنذار 2",
    "وحدة الإنذار 2",
    "قيمة الإنذار 3",
    "وحدة الإنذار 3",
)
CONDITION_FIELDS_BY_UNIT = {
    "كم": "interval_km",
    "ساعة تشغيل": "interval_hours",
    "يوم": "interval_days",
}
WARNING_FIELDS_BY_UNIT = {
    "كم": "warning_km",
    "ساعة تشغيل": "warning_hours",
    "يوم": "warning_days",
}


def build_operation_import_template(*, group_names: list[str]) -> bytes:
    """Create a blank, validated workbook reusable for any model-operation import."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "العمليات"
    sheet.sheet_view.rightToLeft = True
    sheet.append(OPERATION_IMPORT_HEADERS)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:O{MAX_OPERATION_IMPORT_ROWS + 1}"

    header_fill = PatternFill("solid", fgColor="315F42")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 32

    widths = (32, 42, 28, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18)
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + column)].width = width

    comments = (
        "مطلوب؛ لا يتجاوز 120 حرفًا، ويجب ألا يتكرر داخل الملف.",
        "اختياري.",
        "اختياري؛ اختر اسم مجموعة موجودة أو «بدون مجموعة».",
        "مطلوب؛ أدخل قيمة شرط أكبر من صفر. يمكن إدخال ثلاثة محاور كحد أقصى.",
        "اختر الوحدة من القائمة؛ لا تكتب وحدة أخرى.",
        "اختياري؛ أدخل قيمة شرط أكبر من صفر.",
        "اختر الوحدة من القائمة؛ لا تكتب وحدة أخرى.",
        "اختياري؛ أدخل قيمة شرط أكبر من صفر.",
        "اختر الوحدة من القائمة؛ لا تكتب وحدة أخرى.",
        "مطلوب؛ أدخل قيمة إنذار واحدة على الأقل، أكبر من صفر.",
        "اختر الوحدة من القائمة؛ لا تكتب وحدة أخرى.",
        "اختياري؛ أدخل قيمة إنذار أكبر من صفر.",
        "اختر الوحدة من القائمة؛ لا تكتب وحدة أخرى.",
        "اختياري؛ أدخل قيمة إنذار أكبر من صفر.",
        "اختر الوحدة من القائمة؛ لا تكتب وحدة أخرى.",
    )
    for column, instruction in enumerate(comments, start=1):
        sheet.cell(1, column).comment = Comment(instruction, "Materiel")

    group_sheet = workbook.create_sheet("القوائم")
    group_choices = ["بدون مجموعة", *group_names]
    for row_number, group_name in enumerate(group_choices, start=1):
        group_sheet.cell(row_number, 1, group_name)
    for row_number, unit in enumerate(CONDITION_FIELDS_BY_UNIT, start=1):
        group_sheet.cell(row_number, 2, unit)
    group_sheet.sheet_state = "hidden"
    workbook.defined_names.add(DefinedName(
        "MaintenanceGroupOptions",
        attr_text=f"'القوائم'!$A$1:$A${len(group_choices)}",
    ))
    workbook.defined_names.add(DefinedName(
        "MaintenanceUnitOptions",
        attr_text=f"'القوائم'!$B$1:$B${len(CONDITION_FIELDS_BY_UNIT)}",
    ))

    groups_validation = DataValidation(type="list", formula1="=MaintenanceGroupOptions", allow_blank=True)
    groups_validation.error = "اختر مجموعة من القائمة أو اترك الحقل فارغًا."
    groups_validation.errorTitle = "مجموعة غير معروفة"
    groups_validation.errorStyle = "stop"
    groups_validation.showErrorMessage = True
    sheet.add_data_validation(groups_validation)
    groups_validation.add(f"C2:C{MAX_OPERATION_IMPORT_ROWS + 1}")

    unit_validation = DataValidation(
        type="list", formula1="=MaintenanceUnitOptions", allow_blank=True,
    )
    unit_validation.error = "اختر وحدة من القائمة: كم، ساعة تشغيل، أو يوم."
    unit_validation.errorTitle = "وحدة غير صالحة"
    unit_validation.errorStyle = "stop"
    unit_validation.showErrorMessage = True
    sheet.add_data_validation(unit_validation)
    for column in (5, 7, 9, 11, 13, 15):
        letter = chr(64 + column)
        unit_validation.add(f"{letter}2:{letter}{MAX_OPERATION_IMPORT_ROWS + 1}")

    for column in (4, 6, 8, 10, 12, 14):
        positive_decimal = DataValidation(
            type="decimal", operator="greaterThan", formula1="0", allow_blank=True,
        )
        positive_decimal.error = "أدخل قيمة أكبر من صفر."
        positive_decimal.errorTitle = "قيمة غير صالحة"
        positive_decimal.showErrorMessage = True
        sheet.add_data_validation(positive_decimal)
        letter = chr(64 + column)
        positive_decimal.add(f"{letter}2:{letter}{MAX_OPERATION_IMPORT_ROWS + 1}")

    instructions = workbook.create_sheet("إرشادات")
    instructions.sheet_view.rightToLeft = True
    instructions.append(("قالب استيراد عمليات الصيانة",))
    instructions.append(("هذا قالب عام؛ يحدد المستخدم الطراز المستهدف عند رفع الملف إلى البرنامج.",))
    instructions.append(("أدخل كل عملية في صف مستقل بورقة «العمليات»، ولا تغيّر أسماء الأعمدة أو ترتيبها.",))
    instructions.append(("أدخل قيمة الشرط ثم اختر وحدتها من القائمة. يمكن إدخال شرطين معًا مثل كم وأيام.",))
    instructions.append(("كل عملية تحتاج شرطًا واحدًا على الأقل وإنذارًا واحدًا على الأقل؛ يمكن إضافة محاور أخرى.",))
    instructions.append(("اختر وحدات الشرط والإنذار من القوائم؛ كل وحدة لا تتكرر داخل شروطها أو إنذاراتها.",))
    instructions.append(("إذا كانت الوحدة يومًا، أدخل عددًا صحيحًا. اترك أزواج القيم والوحدات غير المستخدمة فارغة.",))
    instructions.append(("اسم المجموعة اختياري؛ اختر مجموعة من القائمة أو اترك الحقل فارغًا.",))
    instructions.column_dimensions["A"].width = 110
    for row in instructions.iter_rows():
        for cell in row:
            cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
    instructions["A1"].font = Font(name="Arial", bold=True, size=14, color="315F42")
    instructions.row_dimensions[1].height = 26

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _clean_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _identity(value: str) -> str:
    return unicodedata.normalize("NFKC", _clean_text(value)).casefold()


def _number(value, *, field: str, row_number: int) -> Decimal | None:
    if value is None or _clean_text(value) == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"الصف {row_number}: أدخل رقمًا صالحًا في «{field}».")
    normalized = _clean_text(value).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    normalized = normalized.replace("٬", "").replace(",", "").replace("٫", ".")
    try:
        parsed = Decimal(normalized)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"الصف {row_number}: أدخل رقمًا صالحًا في «{field}».") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"الصف {row_number}: يجب أن تكون قيمة «{field}» أكبر من صفر.")
    return parsed


def _validate_unit(value, *, field: str, allowed: tuple[str, ...], row_number: int) -> str | None:
    unit = _clean_text(value)
    if not unit:
        return None
    if unit not in allowed:
        choices = "، ".join(allowed)
        raise ValueError(f"الصف {row_number}: وحدة «{field}» غير صالحة. اختر: {choices}.")
    return unit


def _parse_axis_pairs(
    values: list,
    *,
    start_index: int,
    slot_count: int,
    field_name: str,
    fields_by_unit: dict[str, str],
    row_number: int,
    required: bool,
) -> dict:
    parsed = {field: None for field in fields_by_unit.values()}
    selected_units: set[str] = set()
    for slot in range(slot_count):
        value_index = start_index + slot * 2
        value = _number(
            values[value_index] if value_index < len(values) else None,
            field=f"قيمة {field_name} {slot + 1}",
            row_number=row_number,
        )
        unit = _validate_unit(
            values[value_index + 1] if value_index + 1 < len(values) else None,
            field=field_name,
            allowed=tuple(fields_by_unit),
            row_number=row_number,
        )
        if value is None and unit is None:
            continue
        if value is None or unit is None:
            raise ValueError(f"الصف {row_number}: أدخل قيمة {field_name} ووحدتها معًا.")
        if unit in selected_units:
            raise ValueError(f"الصف {row_number}: لا تكرر وحدة «{unit}» ضمن {field_name}.")
        if unit == "يوم" and value != value.to_integral_value():
            raise ValueError(f"الصف {row_number}: قيمة {field_name} بالأيام يجب أن تكون عددًا صحيحًا.")
        field = fields_by_unit[unit]
        parsed[field] = int(value) if unit == "يوم" else value
        selected_units.add(unit)

    if required and not selected_units:
        raise ValueError(f"الصف {row_number}: أدخل قيمة {field_name} واحدة على الأقل مع وحدتها.")
    return parsed


def parse_operation_workbook(data: bytes, groups: list[MaintenanceOperationGroup]) -> list[dict]:
    """Validate the expected workbook structure and return normalized rows."""
    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except (InvalidFileException, ValueError, zipfile.BadZipFile, OSError) as exc:
        raise ValueError("تعذر قراءة الملف. ارفع ملف Excel صالحًا بصيغة .xlsx.") from exc
    try:
        if "العمليات" not in workbook.sheetnames:
            raise ValueError("يجب أن يحتوي الملف على ورقة باسم «العمليات».")
        sheet = workbook["العمليات"]
        headers = tuple(_clean_text(cell) for cell in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ()))
        if headers != OPERATION_IMPORT_HEADERS:
            expected_headers = "، ".join(OPERATION_IMPORT_HEADERS)
            raise ValueError(f"رؤوس الأعمدة أو ترتيبها غير مطابق. استخدم الترتيب التالي: {expected_headers}.")

        group_lookup: dict[str, int] = {}
        ambiguous_groups: set[str] = set()
        for group in groups:
            key = _identity(group.name)
            if key in group_lookup and group_lookup[key] != group.id:
                ambiguous_groups.add(key)
            group_lookup[key] = group.id

        rows: list[dict] = []
        seen_names: set[str] = set()
        row_count = 0
        for row_number, values in enumerate(sheet.iter_rows(min_row=2, max_col=len(OPERATION_IMPORT_HEADERS), values_only=True), start=2):
            values = list(values)
            if not any(_clean_text(value) for value in values):
                continue
            row_count += 1
            if row_count > MAX_OPERATION_IMPORT_ROWS:
                raise ValueError(f"الحد الأقصى {MAX_OPERATION_IMPORT_ROWS} عملية في الملف الواحد.")

            name = _clean_text(values[0] if len(values) > 0 else None)
            description = _clean_text(values[1] if len(values) > 1 else None)
            group_name = _clean_text(values[2] if len(values) > 2 else None)

            if not name:
                raise ValueError(f"الصف {row_number}: اسم العملية مطلوب.")
            if len(name) > 120:
                raise ValueError(f"الصف {row_number}: اسم العملية لا يتجاوز 120 حرفًا.")
            name_key = _identity(name)
            if name_key in seen_names:
                raise ValueError(f"الصف {row_number}: العملية «{name}» مكررة داخل الملف.")
            seen_names.add(name_key)

            group_id = None
            if group_name and group_name != GROUP_NO_VALUE:
                group_key = _identity(group_name)
                if group_key in ambiguous_groups:
                    raise ValueError(f"الصف {row_number}: اسم المجموعة «{group_name}» غير فريد في البرنامج.")
                if group_key not in group_lookup:
                    raise ValueError(f"الصف {row_number}: المجموعة «{group_name}» غير موجودة في مكتبة البرنامج.")
                group_id = group_lookup[group_key]

            condition = _parse_axis_pairs(
                values,
                start_index=3,
                slot_count=MAX_CONDITION_AXES,
                field_name="الشرط",
                fields_by_unit=CONDITION_FIELDS_BY_UNIT,
                row_number=row_number,
                required=True,
            )
            warnings = _parse_axis_pairs(
                values,
                start_index=3 + MAX_CONDITION_AXES * 2,
                slot_count=MAX_WARNING_AXES,
                field_name="الإنذار",
                fields_by_unit=WARNING_FIELDS_BY_UNIT,
                row_number=row_number,
                required=True,
            )

            rows.append({
                "name": name,
                "description": description or None,
                "group_id": group_id,
                **warnings,
                "condition": condition,
            })

        if not rows:
            raise ValueError("أضف عملية واحدة على الأقل في ورقة «العمليات».")
        return rows
    finally:
        workbook.close()


def import_model_operations(db: Session, *, model_id: int, data: bytes) -> int:
    """Create model-scoped operations atomically, including each model condition."""
    model = db.get(EquipmentModel, model_id)
    if model is None:
        raise ValueError("الطراز المحدد غير موجود.")

    groups = db.query(MaintenanceOperationGroup).order_by(
        MaintenanceOperationGroup.sort_order,
        MaintenanceOperationGroup.name,
    ).all()
    rows = parse_operation_workbook(data, groups)

    existing_names = {
        _identity(name)
        for (name,) in db.query(MaintenanceModelOperation.name).filter(
            MaintenanceModelOperation.equipment_model_id == model_id,
        ).all()
    }
    conflicts = [row["name"] for row in rows if _identity(row["name"]) in existing_names]
    if conflicts:
        names = "، ".join(conflicts[:5])
        suffix = " وغيرها" if len(conflicts) > 5 else ""
        raise ValueError(f"توجد عمليات بهذا الاسم في مكتبة الطراز مسبقًا: {names}{suffix}. لم يُستورد أي صف.")

    try:
        for row in rows:
            operation = MaintenanceModelOperation(
                equipment_model_id=model_id,
                name=row["name"],
                description=row["description"],
                group_id=row["group_id"],
                warning_km=row["warning_km"],
                warning_hours=row["warning_hours"],
                warning_days=row["warning_days"],
                interval_km=row["condition"]["interval_km"],
                interval_hours=row["condition"]["interval_hours"],
                interval_days=row["condition"]["interval_days"],
                is_active=True,
            )
            db.add(operation)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ValueError("تعذر حفظ العمليات. أُلغي الاستيراد بالكامل؛ راجع حالة قاعدة البيانات ثم أعد المحاولة.") from exc
    return len(rows)
