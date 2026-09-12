from pathlib import Path
from openpyxl import Workbook

OUTPUT = Path("Materiel_Master_Data_Template.xlsx")


def add_sheet(wb, name, headers, example=None):
    ws = wb.create_sheet(name)
    ws.append(headers)
    if example:
        ws.append(example)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for column in ws.columns:
        width = max(len(str(cell.value or "")) for cell in column) + 2
        ws.column_dimensions[column[0].column_letter].width = min(max(width, 12), 32)


wb = Workbook()
wb.remove(wb.active)
add_sheet(wb, "Categories", ["code", "name", "sort_order"], ["VEH", "مركبات", 1])
add_sheet(wb, "Types", ["name", "measurement_unit", "theoretical_quantity", "category_code"], ["سيارة", "km", None, "VEH"])
add_sheet(wb, "Brands", ["name"], ["Toyota"])
add_sheet(wb, "Models", ["name", "type_name", "brand_name", "tire_config_code", "battery_config_code", "mobility_type", "requires_driver"], ["Land Cruiser 79", "سيارة", "Toyota", "TY_4X4_05", "BAT_24V_02", "mobile", 1])
add_sheet(wb, "TirePositions", ["config_code", "config_name", "item_code", "item_name", "axle_number", "side", "position_type", "sort_order"], ["TY_4X4_05", "4 مواضع + احتياطي", "FL", "أمامي يسار", 1, "L", "main", 1])
add_sheet(wb, "BatteryConfigurations", ["config_code", "config_name", "item_code", "item_name", "value_number", "unit", "value_text"], ["BAT_24V_02", "بطاريتان 12V", "B1", "البطارية 1", 12, "V", ""])
add_sheet(wb, "ModelProperties", ["model_name", "type_name", "brand_name", "property_key", "property_label", "value_text", "value_number", "unit", "sort_order"], ["Land Cruiser 79", "سيارة", "Toyota", "engine", "المحرك", "Diesel", None, None, 1])
wb.save(OUTPUT)
print(OUTPUT)
