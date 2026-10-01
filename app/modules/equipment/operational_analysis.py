from collections import defaultdict
from decimal import Decimal


def build_operational_analysis(items, faults, maintenance_records):
    """Relate utilization context to faults, maintenance and technical readiness.

    This is descriptive analysis: it surfaces observed patterns and does not
    infer causation from correlation.
    """
    by_id = {item.id: item for item in items}
    faults_by_equipment = defaultdict(list)
    maintenance_by_equipment = defaultdict(list)

    for fault in faults:
        faults_by_equipment[fault.equipment_id].append(fault)
    for record in maintenance_records:
        maintenance_by_equipment[record.equipment_id].append(record)

    rows = []
    totals = {
        "faults": 0,
        "open_faults": 0,
        "critical_high_faults": 0,
        "prohibited_faults": 0,
        "maintenance_records": 0,
        "scheduled_maintenance": 0,
    }

    for equipment_id, item in by_id.items():
        equipment_faults = faults_by_equipment[equipment_id]
        equipment_maintenance = maintenance_by_equipment[equipment_id]
        open_faults = [f for f in equipment_faults if f.status not in ("repaired", "closed")]
        severe_faults = [f for f in equipment_faults if f.severity in ("high", "critical")]
        prohibited_faults = [f for f in equipment_faults if f.exploitation_impact == "prohibited"]
        scheduled = [r for r in equipment_maintenance if r.is_scheduled]

        totals["faults"] += len(equipment_faults)
        totals["open_faults"] += len(open_faults)
        totals["critical_high_faults"] += len(severe_faults)
        totals["prohibited_faults"] += len(prohibited_faults)
        totals["maintenance_records"] += len(equipment_maintenance)
        totals["scheduled_maintenance"] += len(scheduled)

        rows.append({
            "equipment_id": equipment_id,
            "registration_number": item.registration_number,
            "model": item.equipment_model.name if item.equipment_model else "بدون طراز",
            "fault_count": len(equipment_faults),
            "open_fault_count": len(open_faults),
            "severe_fault_count": len(severe_faults),
            "prohibited_fault_count": len(prohibited_faults),
            "maintenance_count": len(equipment_maintenance),
            "scheduled_maintenance_count": len(scheduled),
            "last_fault_date": max((f.reported_date for f in equipment_faults), default=None),
            "last_maintenance_date": max((r.maintenance_date for r in equipment_maintenance), default=None),
        })

    findings = []
    if totals["open_faults"]:
        findings.append({
            "state": "أعطال مفتوحة",
            "evidence": f'يوجد {totals["open_faults"]} عطل غير مغلق ضمن السجلات الحالية.',
            "meaning": "هذا يحدد عبء الأعطال القائم ويُقرأ مع حالة الجاهزية، دون افتراض سبب فني.",
        })
    if totals["critical_high_faults"]:
        findings.append({
            "state": "أعطال عالية الأهمية",
            "evidence": f'يوجد {totals["critical_high_faults"]} عطل بدرجة high أو critical.',
            "meaning": "يُستخدم لتحديد مواضع تحتاج متابعة تشغيلية وفنية أدق.",
        })
    if totals["prohibited_faults"]:
        findings.append({
            "state": "تأثير يمنع الاستغلال",
            "evidence": f'هناك {totals["prohibited_faults"]} عطل مسجل بتأثير prohibited على الاستغلال.',
            "meaning": "يربط سجل العطل مباشرة بالقيود التشغيلية المسجلة في النظام.",
        })
    if totals["maintenance_records"]:
        findings.append({
            "state": "نشاط الصيانة",
            "evidence": f'تم تسجيل {totals["maintenance_records"]} سجل صيانة، منها {totals["scheduled_maintenance"]} مجدول.',
            "meaning": "يُقارن مع عبء الأعطال والاستغلال لفهم نمط الخدمة الفعلي.",
        })

    return {"rows": rows, "totals": totals, "findings": findings}
