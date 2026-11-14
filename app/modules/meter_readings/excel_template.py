from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation


HEADERS = ("الطراز", "رقم التسجيل", "التاريخ", "الكيلومترات", "الساعات", "حالة العداد")
MAX_TEMPLATE_ROWS = 1000


def build_template() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "قراءات العداد"
    sheet.sheet_view.rightToLeft = True
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:F{MAX_TEMPLATE_ROWS + 1}"
    sheet.append(HEADERS)

    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="176B5B")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 28

    for column, width in zip("ABCDEF", (30, 22, 16, 19, 16, 18)):
        sheet.column_dimensions[column].width = width

    for row_number in range(2, MAX_TEMPLATE_ROWS + 2):
        sheet.cell(row_number, 2).number_format = "@"
        sheet.cell(row_number, 3).number_format = "yyyy-mm-dd"
        sheet.cell(row_number, 4).number_format = "#,##0.###"
        sheet.cell(row_number, 5).number_format = "#,##0.###"

    status_validation = DataValidation(
        type="list",
        formula1='"يعمل,لا يعمل"',
        allow_blank=True,
        showErrorMessage=True,
        errorStyle="stop",
        errorTitle="حالة غير صحيحة",
        error="اختر يعمل أو لا يعمل.",
    )
    sheet.add_data_validation(status_validation)
    status_validation.add(f"F2:F{MAX_TEMPLATE_ROWS + 1}")

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
