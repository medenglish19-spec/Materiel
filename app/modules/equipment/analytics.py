"""Transparent, rule-based fleet analysis.

This module deliberately avoids opaque scores. It derives findings from the
current equipment state and the approved type-level theoretical quantity.
Historical persistence and institutional mission requirements are future inputs.
"""

from collections import OrderedDict


TECHNICAL_STATES = ("ready", "ready_restricted", "broken")
OPERATIONAL_STATES = (
    "available",
    "in_mission",
    "in_maintenance",
    "in_external_workshop",
    "unavailable",
)


def build_capacity_readiness_analysis(items):
    """Build the first institutional analysis axis: capacity and readiness.

    Theoretical quantity belongs to EquipmentType, so numerical adequacy is
    evaluated at type level. Model rows never inherit a type requirement.
    Technical readiness and operational availability remain separate axes.
    """
    groups = OrderedDict()

    for item in items:
        equipment_type = item.equipment_type
        category = equipment_type.category if equipment_type else None
        category_name = category.name if category else "غير مصنف"
        type_name = equipment_type.name if equipment_type else "بدون نوع"
        theoretical = int(equipment_type.theoretical_quantity or 0) if equipment_type else 0

        cg = groups.setdefault(
            category_name,
            {"name": category_name, "theoretical": 0, "actual": 0, "types": OrderedDict()},
        )
        tg = cg["types"].setdefault(
            type_name,
            {
                "name": type_name,
                "theoretical": theoretical,
                "actual": 0,
                "ready": 0,
                "ready_restricted": 0,
                "broken": 0,
                "available": 0,
                "in_mission": 0,
                "in_maintenance": 0,
                "in_external_workshop": 0,
                "unavailable": 0,
                "ready_available": 0,
                "ready_not_available": 0,
                "models": OrderedDict(),
            },
        )
        tg["theoretical"] = theoretical
        tg["actual"] += 1
        cg["actual"] += 1

        condition = item.technical_condition if item.technical_condition in TECHNICAL_STATES else "broken"
        tg[condition] += 1

        operational = item.operational_status if item.operational_status in OPERATIONAL_STATES else "unavailable"
        tg[operational] += 1

        model_name = item.equipment_model.name if item.equipment_model else "بدون طراز"
        brand_name = (
            item.equipment_model.brand.name
            if item.equipment_model and item.equipment_model.brand
            else ""
        )
        model_key = (brand_name, model_name)
        mg = tg["models"].setdefault(
            model_key,
            {
                "name": f"{brand_name} — {model_name}" if brand_name else model_name,
                "actual": 0,
                "ready": 0,
                "ready_restricted": 0,
                "broken": 0,
                "available": 0,
                "in_mission": 0,
                "in_maintenance": 0,
                "in_external_workshop": 0,
                "unavailable": 0,
            },
        )
        mg["actual"] += 1
        mg[condition] += 1
        mg[operational] += 1
        if condition == "ready" and operational == "available":
            tg["ready_available"] += 1
        elif condition == "ready" and operational != "available":
            tg["ready_not_available"] += 1

    def finalize(row):
        known_requirement = row["theoretical"] > 0
        row["need"] = max(row["theoretical"] - row["actual"], 0) if known_requirement else 0
        row["surplus"] = max(row["actual"] - row["theoretical"], 0) if known_requirement else 0
        row["outside_requirement"] = row["actual"] if not known_requirement else 0
        row["readiness_pct"] = (row["ready"] / row["actual"] * 100) if row["actual"] else 0.0
        row["restricted_pct"] = (
            row["ready_restricted"] / row["actual"] * 100 if row["actual"] else 0.0
        )
        row["broken_pct"] = (row["broken"] / row["actual"] * 100) if row["actual"] else 0.0
        row["available_pct"] = (
            row["available"] / row["actual"] * 100 if row["actual"] else 0.0
        )
        row["ready_available_pct"] = (
            row["ready_available"] / row["actual"] * 100 if row["actual"] else 0.0
        )
        row["technical_but_not_available"] = row["ready_not_available"]
        row["known_requirement"] = known_requirement
        return row

    categories = []
    for category in groups.values():
        types = []
        for type_row in category["types"].values():
            finalize(type_row)
            type_row["models"] = list(type_row["models"].values())
            types.append(type_row)
        category["types"] = types
        category["theoretical"] = sum(t["theoretical"] for t in types)
        category["outside_requirement"] = sum(t["outside_requirement"] for t in types)
        category["ready_available"] = sum(t["ready_available"] for t in types)
        category["ready_not_available"] = sum(t["ready_not_available"] for t in types)
        finalize(category)
        categories.append(category)

    totals = {
        "theoretical": sum(c["theoretical"] for c in categories),
        "actual": sum(c["actual"] for c in categories),
        "ready": sum(c["ready"] for c in categories),
        "ready_restricted": sum(c["ready_restricted"] for c in categories),
        "broken": sum(c["broken"] for c in categories),
        "available": sum(c["available"] for c in categories),
        "in_mission": sum(c["in_mission"] for c in categories),
        "in_maintenance": sum(c["in_maintenance"] for c in categories),
        "in_external_workshop": sum(c["in_external_workshop"] for c in categories),
        "unavailable": sum(c["unavailable"] for c in categories),
        "ready_available": sum(c["ready_available"] for c in categories),
        "ready_not_available": sum(c["ready_not_available"] for c in categories),
        "outside_requirement": sum(c["outside_requirement"] for c in categories),
    }
    finalize(totals)
    totals["outside_requirement"] = sum(c["outside_requirement"] for c in categories)

    findings = []
    if totals["need"]:
        findings.append({
            "state": "فجوة عددية",
            "subject": "الحضيرة",
            "evidence": f'احتياج عددي مثبت في الأنواع ذات النظري المعتمد: {totals["need"]} وحدة.',
            "meaning": "التعداد الفعلي لا يغطي كامل التعداد النظري المعتمد.",
        })
    if totals["broken"]:
        findings.append({
            "state": "قيد فني",
            "subject": "الحضيرة",
            "evidence": f'{totals["broken"]} وحدة مصنفة عاطلة ({totals["broken_pct"]:.1f}%).',
            "meaning": "جزء من التعداد المحقق غير قادر فنيًا على العمل وفق الحالة المسجلة.",
        })
    if totals["technical_but_not_available"]:
        findings.append({
            "state": "قيد تشغيلي",
            "subject": "الحضيرة",
            "evidence": (
                f'{totals["technical_but_not_available"]} وحدة جاهزة فنيًا '
                "لكنها ليست في حالة تشغيلية «متاح»."
            ),
            "meaning": "الجاهزية الفنية لا تساوي الإتاحة التشغيلية؛ يلزم فحص سبب الوضعية التشغيلية.",
        })
    if totals["outside_requirement"]:
        findings.append({
            "state": "متطلبات غير محددة",
            "subject": "الحضيرة",
            "evidence": (
                f'{totals["outside_requirement"]} وحدة تتبع أنواعًا بلا تعداد نظري معتمد.'
            ),
            "meaning": "لا ينبغي إدخال هذه الوحدات في حساب الاحتياج أو الفائض قبل تعريف المرجع النظري.",
        })

    for type_row in [t for c in categories for t in c["types"]]:
        if type_row["need"]:
            findings.append({
                "state": "فجوة عددية",
                "subject": type_row["name"],
                "evidence": (
                    f'نظري {type_row["theoretical"]} مقابل محقق {type_row["actual"]}؛ '
                    f'الاحتياج {type_row["need"]}.'
                ),
                "meaning": "يوجد نقص عددي على مستوى هذا النوع وفق التعداد النظري المسجل.",
            })
        if type_row["broken"]:
            findings.append({
                "state": "قيد فني",
                "subject": type_row["name"],
                "evidence": (
                    f'{type_row["broken"]} عاطل من أصل {type_row["actual"]} '
                    f'({type_row["broken_pct"]:.1f}%).'
                ),
                "meaning": "القدرة المتاحة لهذا النوع أقل من التعداد المحقق بسبب الحالة الفنية المسجلة.",
            })
        if type_row["technical_but_not_available"]:
            findings.append({
                "state": "قيد تشغيلي",
                "subject": type_row["name"],
                "evidence": (
                    f'{type_row["technical_but_not_available"]} جاهز فنيًا '
                    "لكن وضعه التشغيلي ليس «متاح»."
                ),
                "meaning": "توجد فجوة بين الحالة الفنية والوضع التشغيلي لهذا النوع.",
            })

    return {
        "categories": categories,
        "totals": totals,
        "findings": findings,
        "definitions": {
            "numerical_gap": "النظري − المحقق، للأنواع ذات التعداد النظري المعتمد فقط.",
            "technical_readiness": "جاهز ÷ المحقق.",
            "operational_availability": "متاح ÷ المحقق.",
            "ready_available": "عدد الوحدات التي تجمع بين الجاهزية الفنية وحالة التشغيل «متاح».",
            "outside_requirement": "وحدات تنتمي إلى أنواع بلا تعداد نظري معتمد؛ لا تدخل في الاحتياج أو الفائض.",
        },
    }
