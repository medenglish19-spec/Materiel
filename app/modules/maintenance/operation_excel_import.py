"""Excel template and direct importer for model-scoped maintenance operations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
import unicodedata
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.equipment_types.models import EquipmentModel
from app.modules.maintenance.models import (
    MaintenanceModelOperation,
    MaintenanceOperationGroup,
)


OPERATION_IMPORT_HEADERS = (
    "العملية",
    "الوصف",
    "المجموعة",
    "قيمة الإنذار",
    "وحدة الإنذار",
    "قيمة الشرط",
    "وحدة الشرط",
)

WARNING_UNITS = ("كم", "يوم")
CONDITION_UNITS = ("كم", "ساعة تشغيل", "يوم")
GROUP_NO_VALUE = "بدون مجموعة"
MAX_OPERATION_IMPORT_ROWS = 2000


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
    aliases = {
        "كيلومتر": "كم",
        "كيلومترات": "كم",
        "ساعات تشغيل": "ساعة تشغيل",
        "ساعات": "ساعة تشغيل",
        "أيام": "يوم",
    }
    unit = aliases.get(unit, unit)
    if unit not in allowed:
        choices = "، ".join(allowed)
        raise ValueError(f"الصف {row_number}: وحدة «{field}» غير صالحة. اختر: {choices}.")
    return unit


def create_operation_template(group_names: list[str]) -> bytes:
    """Create the user-facing workbook with dropdowns matching program values."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "العمليات"
    sheet.sheet_view.rightToLeft = True
    sheet.freeze_panes = "A2"
    sheet.append(OPERATION_IMPORT_HEADERS)
    sheet.auto_filter.ref = f"A1:G{MAX_OPERATION_IMPORT_ROWS + 1}"

    header_fill = PatternFill("solid", fgColor="28674A")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(name="Arial", color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 32
    for column, width in {
        "A": 36, "B": 46, "C": 26, "D": 16, "E": 18, "F": 16, "G": 20,
    }.items():
        sheet.column_dimensions[column].width = width
    for row in range(2, MAX_OPERATION_IMPORT_ROWS + 2):
        sheet.cell(row, 4).number_format = "0.##"
        sheet.cell(row, 6).number_format = "0.##"

    lists = workbook.create_sheet("القوائم")
    lists.sheet_view.rightToLeft = True
    lists.append(["المجموعات", "وحدات الإنذار", "وحدات الشرط"])
    groups = [GROUP_NO_VALUE, *sorted({name.strip() for name in group_names if name and name.strip()})]
    for index, value in enumerate(groups, start=2):
        cell = lists.cell(index, 1, value)
        cell.data_type = "s"
    for index, value in enumerate(WARNING_UNITS, start=2):
        lists.cell(index, 2, value)
    for index, value in enumerate(CONDITION_UNITS, start=2):
        lists.cell(index, 3, value)
    lists.sheet_state = "hidden"

    workbook.defined_names.add(DefinedName(
        "MaintenanceGroupOptions",
        attr_text=f"'القوائم'!$A$2:$A${max(2, len(groups) + 1)}",
    ))
    workbook.defined_names.add(DefinedName(
        "MaintenanceWarningUnits",
        attr_text=f"'القوائم'!$B$2:$B${len(WARNING_UNITS) + 1}",
    ))
    workbook.defined_names.add(DefinedName(
        "MaintenanceConditionUnits",
        attr_text=f"'القوائم'!$C$2:$C${len(CONDITION_UNITS) + 1}",
    ))

    group_validation = DataValidation(type="list", formula1="=MaintenanceGroupOptions", allow_blank=True)
    group_validation.errorTitle = "مجموعة غير معتمدة"
    group_validation.error = "اختر مجموعة من القائمة الموجودة في البرنامج أو اترك الحقل فارغًا."
    group_validation.showErrorMessage = True
    sheet.add_data_validation(group_validation)
    group_validation.add(f"C2:C{MAX_OPERATION_IMPORT_ROWS + 1}")

    warning_units = DataValidation(type="list", formula1="=MaintenanceWarningUnits", allow_blank=True)
    warning_units.errorTitle = "وحدة غير معتمدة"
    warning_units.error = "اختر كم أو يومًا من القائمة."
    warning_units.showErrorMessage = True
    sheet.add_data_validation(warning_units)
    warning_units.add(f"E2:E{MAX_OPERATION_IMPORT_ROWS + 1}")

    condition_units = DataValidation(type="list", formula1="=MaintenanceConditionUnits", allow_blank=True)
    condition_units.errorTitle = "وحدة غير معتمدة"
    condition_units.error = "اختر كم أو ساعة تشغيل أو يومًا من القائمة."
    condition_units.showErrorMessage = True
    sheet.add_data_validation(condition_units)
    condition_units.add(f"G2:G{MAX_OPERATION_IMPORT_ROWS + 1}")

    positive_number = DataValidation(type="decimal", operator="greaterThan", formula1="0", allow_blank=True)
    positive_number.errorTitle = "قيمة غير صالحة"
    positive_number.error = "أدخل رقمًا أكبر من صفر."
    positive_number.showErrorMessage = True
    sheet.add_data_validation(positive_number)
    positive_number.add(f"D2:D{MAX_OPERATION_IMPORT_ROWS + 1}")
    positive_number.add(f"F2:F{MAX_OPERATION_IMPORT_ROWS + 1}")

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def parse_operation_workbook(data: bytes, groups: list[MaintenanceOperationGroup]) -> list[dict]:
    """Validate the fixed template and return normalized rows without writing."""
    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except (InvalidFileException, ValueError, zipfile.BadZipFile, OSError) as exc:
        raise ValueError("تعذر قراءة الملف. ارفع قالب Excel بصيغة .xlsx.") from exc
    try:
        if "العمليات" not in workbook.sheetnames:
            raise ValueError("الملف لا يحتوي على ورقة «العمليات» من القالب المعتمد.")
        sheet = workbook["العمليات"]
        headers = tuple(_clean_text(cell) for cell in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ()))
        if headers != OPERATION_IMPORT_HEADERS:
            raise ValueError("رؤوس الأعمدة لا تطابق قالب عمليات الصيانة المعتمد. نزّل قالبًا جديدًا من البرنامج.")

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
        for row_number, values in enumerate(sheet.iter_rows(min_row=2, max_col=7, values_only=True), start=2):
            values = list(values)
            if not any(_clean_text(value) for value in values):
                continue
            row_count += 1
            if row_count > MAX_OPERATION_IMPORT_ROWS:
                raise ValueError(f"القالب يقبل حتى {MAX_OPERATION_IMPORT_ROWS} عملية في الملف الواحد.")

            name = _clean_text(values[0] if len(values) > 0 else None)
            description = _clean_text(values[1] if len(values) > 1 else None)
            group_name = _clean_text(values[2] if len(values) > 2 else None)
            warning_value_cell = values[3] if len(values) > 3 else None
            warning_unit_cell = values[4] if len(values) > 4 else None
            condition_value_cell = values[5] if len(values) > 5 else None
            condition_unit_cell = values[6] if len(values) > 6 else None

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

            warning_value = _number(warning_value_cell, field="قيمة الإنذار", row_number=row_number)
            warning_unit = _validate_unit(
                warning_unit_cell, field="الإنذار", allowed=WARNING_UNITS, row_number=row_number,
            )
            if (warning_value is None) != (warning_unit is None):
                raise ValueError(f"الصف {row_number}: أدخل قيمة الإنذار ووحدته معًا، أو اتركهما فارغين.")

            condition_value = _number(condition_value_cell, field="قيمة الشرط", row_number=row_number)
            condition_unit = _validate_unit(
                condition_unit_cell, field="الشرط", allowed=CONDITION_UNITS, row_number=row_number,
            )
            if condition_value is None or condition_unit is None:
                raise ValueError(f"الصف {row_number}: شرط الطراز مطلوب؛ أدخل قيمته واختر وحدته.")

            warning_km = None
            warning_days = None
            if warning_unit == "كم":
                warning_km = warning_value
            elif warning_unit == "يوم":
                if warning_value != warning_value.to_integral_value():
                    raise ValueError(f"الصف {row_number}: قيمة إنذار الأيام يجب أن تكون عددًا صحيحًا.")
                warning_days = int(warning_value)

            condition = {"interval_km": None, "interval_hours": None, "interval_days": None}
            if condition_unit == "كم":
                condition["interval_km"] = condition_value
            elif condition_unit == "ساعة تشغيل":
                condition["interval_hours"] = condition_value
            elif condition_unit == "يوم":
                if condition_value != condition_value.to_integral_value():
                    raise ValueError(f"الصف {row_number}: شرط الأيام يجب أن يكون عددًا صحيحًا.")
                condition["interval_days"] = int(condition_value)

            rows.append({
                "name": name,
                "description": description or None,
                "group_id": group_id,
                "warning_km": warning_km,
                "warning_days": warning_days,
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
