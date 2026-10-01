from collections import defaultdict
from decimal import Decimal


CLOSED_FAULT_STATUSES = {"repaired", "closed"}
COMPLETED_REPAIR_STATUS = "completed"


def _decimal(value):
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None


def build_operational_analysis(items, faults, maintenance_records, repairs=None, utilization=None):
    """Relate utilization, faults, repairs, maintenance and current state.

    Findings are descriptive patterns only. No causal conclusion is inferred.
    Meter-derived distance is used when available; no distance is invented.
    """
    utilization = utilization or {}
    repairs = repairs or []
    by_id = {item.id: item for item in items}
    faults_by = defaultdict(list)
    repairs_by = defaultdict(list)
    maintenance_by = defaultdict(list)

    for fault in faults:
        faults_by[fault.equipment_id].append(fault)
    for repair in repairs:
        fault = getattr(repair, "fault", None)
        if fault is not None:
            repairs_by[fault.equipment_id].append(repair)
    for record in maintenance_records:
        maintenance_by[record.equipment_id].append(record)

    utilization_rows = {r["equipment_id"]: r for r in utilization.get("rows", [])}
    rows = []
    totals = {
        "faults": 0, "open_faults": 0, "critical_high_faults": 0,
        "prohibited_faults": 0, "repairs": 0, "completed_repairs": 0,
        "labor_hours": Decimal("0"), "external_repairs": 0,
        "maintenance_records": 0, "scheduled_maintenance": 0,
    }

    for equipment_id, item in by_id.items():
        fs = faults_by[equipment_id]
        rs = repairs_by[equipment_id]
        ms = maintenance_by[equipment_id]
        u = utilization_rows.get(equipment_id, {})
        distance = _decimal(u.get("distance_km"))
        open_fs = [f for f in fs if f.status not in CLOSED_FAULT_STATUSES]
        severe = [f for f in fs if f.severity in ("high", "critical")]
        prohibited = [f for f in fs if f.exploitation_impact == "prohibited"]
        completed = [r for r in rs if r.status == COMPLETED_REPAIR_STATUS]
        external = [r for r in rs if r.workshop_type == "external"]
        labor = sum((_decimal(r.labor_hours) or Decimal("0") for r in rs), Decimal("0"))
        scheduled = [m for m in ms if m.is_scheduled]
        fault_rate = (
            Decimal(len(fs)) / distance * Decimal("1000")
            if distance and distance > 0 else None
        )

        totals["faults"] += len(fs)
        totals["open_faults"] += len(open_fs)
        totals["critical_high_faults"] += len(severe)
        totals["prohibited_faults"] += len(prohibited)
        totals["repairs"] += len(rs)
        totals["completed_repairs"] += len(completed)
        totals["labor_hours"] += labor
        totals["external_repairs"] += len(external)
        totals["maintenance_records"] += len(ms)
        totals["scheduled_maintenance"] += len(scheduled)

        rows.append({
            "equipment_id": equipment_id,
            "registration_number": item.registration_number,
            "model": item.equipment_model.name if item.equipment_model else "بدون طراز",
            "fault_count": len(fs),
            "fault_rate_per_1000km": fault_rate,
            "open_fault_count": len(open_fs),
            "severe_fault_count": len(severe),
            "prohibited_fault_count": len(prohibited),
            "repair_count": len(rs),
            "completed_repair_count": len(completed),
            "labor_hours": labor,
            "external_repair_count": len(external),
            "maintenance_count": len(ms),
            "scheduled_maintenance_count": len(scheduled),
            "distance_km": distance,
            "technical_condition": item.technical_condition,
            "operational_status": item.operational_status,
            "last_fault_date": max((f.reported_date for f in fs), default=None),
            "last_maintenance_date": max((m.maintenance_date for m in ms), default=None),
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

    linked = [r for r in rows if r["distance_km"] and r["distance_km"] > 0]
    if linked:
        with_faults = [r for r in linked if r["fault_count"]]
        if with_faults:
            findings.append({
                "state": "أعطال مرتبطة بمسافة مقاسة",
                "evidence": f'يمكن ربط {len(with_faults)} عتاد بسجل أعطال ومسافة مقاسة بالعداد.',
                "meaning": "تتوفر قاعدة للمقارنة بين عبء الأعطال والاستخدام دون افتراض أن الاستخدام سبب الأعطال.",
            })

    for r in rows:
        if r["fault_count"] >= 3 and r["maintenance_count"] == 0:
            findings.append({
                "state": "سجل يحتاج تحققًا",
                "evidence": f'{r["registration_number"] or "عتاد غير مسجل"} لديه {r["fault_count"]} أعطال مقابل 0 سجل صيانة.',
                "meaning": "قد يعكس نقصًا في تسجيل الصيانة أو نمطًا يستحق التحقق؛ لا يُفسر كسبب أو نتيجة.",
            })

    return {"rows": rows, "totals": totals, "findings": findings}
