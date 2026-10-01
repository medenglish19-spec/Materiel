from collections import defaultdict
from decimal import Decimal


CLOSED_FAULT_STATUSES = {"repaired", "closed"}
COMPLETED_REPAIR_STATUS = "completed"


def _decimal(value):
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None


def _median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / Decimal("2")


def _equipment_labels(item):
    """Return (type_name, brand_name, model_name, peer_key) defensively.

    Equipment may have no type, no model, or a model without a brand, so
    every step is read defensively and nothing is invented: an absent
    brand yields an empty string, an absent model name yields the
    existing "بدون طراز" placeholder, and an unclassified item groups
    under its type name.
    """
    equipment_type = getattr(item, "equipment_type", None)
    type_name = (getattr(equipment_type, "name", "") or "بدون نوع") \
        if equipment_type else "بدون نوع"
    model = getattr(item, "equipment_model", None)
    brand = getattr(model, "brand", None)
    brand_name = (getattr(brand, "name", "") or "") if brand else ""
    model_name = (getattr(model, "name", "") or "بدون طراز") if model else "بدون طراز"
    peer_key = ("model", brand_name, model_name) if model else ("type", type_name)
    return type_name, brand_name, model_name, peer_key


def build_operational_analysis(items, faults, maintenance_records, repairs=None, utilization=None):
    """Build transparent cross-source operational patterns.

    Distances and fuel efficiency come from the utilization analysis, where
    odometer readings are authoritative. Comparisons are descriptive and use
    homogeneous peer groups; no causal conclusion or composite score is made.
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
        mission_distance = _decimal(u.get("mission_distance_km"))
        fuel_liters = _decimal(u.get("fuel_liters"))
        mission_count = int(u.get("mission_count") or 0)
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
        fuel_per_100km = (
            fuel_liters / distance * Decimal("100")
            if fuel_liters is not None and distance and distance > 0 else None
        )

        type_name, brand_name, model_name, peer_key = _equipment_labels(item)

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
            "type": type_name,
            "model": f"{brand_name} — {model_name}" if brand_name else model_name,
            "peer_key": peer_key,
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
            "mission_count": mission_count,
            "mission_distance_km": mission_distance,
            "fuel_liters": fuel_liters,
            "fuel_per_100km": fuel_per_100km,
            # getattr: تُقرأ الحالة إن وُجدت، ولا تُخترع قيمة عند غيابها.
            "technical_condition": getattr(item, "technical_condition", None),
            "operational_status": getattr(item, "operational_status", None),
            "last_fault_date": max((f.reported_date for f in fs), default=None),
            "last_repair_date": max((r.repair_date for r in rs), default=None),
            "last_maintenance_date": max((m.maintenance_date for m in ms), default=None),
        })

    # Establish peer references without turning them into scores.
    peers = defaultdict(list)
    for row in rows:
        peers[row["peer_key"]].append(row)

    findings = []

    for row in rows:
        group = peers[row["peer_key"]]
        other_rows = [p for p in group if p["equipment_id"] != row["equipment_id"]]
        rate_peers = [p["fault_rate_per_1000km"] for p in other_rows if p["fault_rate_per_1000km"] is not None]
        fuel_peers = [p["fuel_per_100km"] for p in other_rows if p["fuel_per_100km"] is not None]

        row["peer_count"] = len(other_rows)
        row["peer_fault_rate_per_1000km"] = _median(rate_peers)
        row["peer_fuel_per_100km"] = _median(fuel_peers)

        if row["fault_rate_per_1000km"] is not None and len(rate_peers) >= 3:
            reference = row["peer_fault_rate_per_1000km"]
            if row["fault_rate_per_1000km"] > reference:
                findings.append({
                    "kind": "finding",
                "state": "عبء أعطال أعلى من المجموعة المماثلة",
                    "subject": row["registration_number"] or "عتاد غير مسجل",
                    "comparison": f'معدل العتاد {row["fault_rate_per_1000km"]:.2f} عطل/1000 كم مقابل وسيط المجموعة {reference:.2f}، اعتمادًا على {len(rate_peers)} وحدات مماثلة قابلة للمقارنة.',
                    "evidence": f'المسافة المقاسة {row["distance_km"]:.1f} كم، والأعطال {row["fault_count"]}.',
                    "meaning": "يظهر عبء أعطال أعلى من الوحدات المماثلة المتاحة للمقارنة؛ يحتاج إلى فحص السجل التفصيلي دون اعتبار ذلك سببًا محددًا.",
                })

        if row["fuel_per_100km"] is not None and len(fuel_peers) >= 3:
            reference = row["peer_fuel_per_100km"]
            if row["fuel_per_100km"] > reference:
                findings.append({
                    "kind": "finding",
                "state": "استهلاك وقود أعلى من المجموعة المماثلة",
                    "subject": row["registration_number"] or "عتاد غير مسجل",
                    "comparison": f'الاستهلاك {row["fuel_per_100km"]:.2f} لتر/100 كم مقابل وسيط المجموعة {reference:.2f}، اعتمادًا على {len(fuel_peers)} وحدات مماثلة قابلة للمقارنة.',
                    "evidence": f'المسافة المقاسة {row["distance_km"]:.1f} كم، والوقود المرتبط بها {row["fuel_liters"]:.1f} لتر.',
                    "meaning": "يظهر استهلاكًا أعلى من الوحدات المماثلة ضمن نفس قاعدة البيانات الزمنية المتاحة؛ لا يثبت سببًا ميكانيكيًا.",
                })

        if row["open_fault_count"] and row["repair_count"]:
            findings.append({
                "kind": "finding",
                "state": "عطل مفتوح مع نشاط إصلاح",
                "subject": row["registration_number"] or "عتاد غير مسجل",
                "comparison": "يوجد سجل إصلاح واحد على الأقل مع بقاء عطل غير مغلق.",
                "evidence": f'{row["open_fault_count"]} عطل مفتوح مقابل {row["repair_count"]} إصلاح.',
                "meaning": "توجد حالة تستحق مراجعة تسلسل العطل والإصلاح وحالته الحالية.",
            })

        if row["prohibited_fault_count"] and (
            row["technical_condition"] != "ready" or row["operational_status"] != "available"
        ):
            findings.append({
                "kind": "finding",
                "state": "قيد استغلال مدعوم بسجل عطل",
                "subject": row["registration_number"] or "عتاد غير مسجل",
                "comparison": f'العطل المانع للاستغلال مقترن بالحالة الحالية: {row["technical_condition"]} / {row["operational_status"]}.',
                "evidence": f'{row["prohibited_fault_count"]} عطل بتأثير يمنع الاستغلال.',
                "meaning": "تتوافق إشارة سجل العطل مع وجود قيد فني أو تشغيلي حالي؛ لا يُستنتج من ذلك سبب القيد.",
            })

        if row["fault_count"] and row["maintenance_count"] and row["repair_count"]:
            findings.append({
                "kind": "context",
                "state": "سجل متكامل للمراجعة",
                "subject": row["registration_number"] or "عتاد غير مسجل",
                "comparison": "الأعطال والإصلاحات والصيانة موجودة معًا لنفس العتاد.",
                "evidence": f'{row["fault_count"]} أعطال، {row["repair_count"]} إصلاحات، {row["maintenance_count"]} سجلات صيانة.',
                "meaning": "يوفر هذا العتاد سجلًا كافيًا نسبيًا لمراجعة العلاقة الزمنية بين الاستغلال والصيانة والأعطال بدل قراءة كل مصدر منفردًا.",
            })

    # Temporal patterns: distinguish a one-off report from recurrence across
    # separate calendar periods. This is descriptive, not a diagnosis.
    temporal_repeated = defaultdict(set)
    for fault in faults:
        item = by_id.get(fault.equipment_id)
        if not item or not fault.fault_type or not fault.reported_date:
            continue
        _type_name, brand_name, model_name, _peer_key = _equipment_labels(item)
        period = fault.reported_date.strftime("%Y-%m")
        temporal_repeated[(fault.equipment_id, brand_name, model_name, fault.fault_type)].add(period)

    for (equipment_id, brand, model, fault_type), periods in temporal_repeated.items():
        if len(periods) >= 2:
            item = by_id.get(equipment_id)
            label = item.registration_number if item and item.registration_number else "عتاد غير مسجل"
            findings.append({
                "kind": "finding",
                "state": "تكرار عطل عبر فترات زمنية",
                "subject": label,
                "comparison": f'نوع العطل «{fault_type}» ظهر في {len(periods)} فترات شهرية مختلفة.',
                "evidence": f'الفترات المسجلة: {", ".join(sorted(periods))}.',
                "meaning": "التكرار عبر فترات منفصلة يجعل الحالة نمطًا زمنيًا يستحق المراجعة، دون إثبات سبب التكرار.",
            })

    # Group-level repeated patterns: same fault type across comparable equipment.
    repeated = defaultdict(list)
    for fault in faults:
        item = by_id.get(fault.equipment_id)
        if not item or not fault.fault_type:
            continue
        _type_name, brand_name, model_name, _peer_key = _equipment_labels(item)
        key = (brand_name, model_name, fault.fault_type)
        repeated[key].append(fault.equipment_id)

    for (brand, model, fault_type), equipment_ids in repeated.items():
        distinct = len(set(equipment_ids))
        if distinct >= 2:
            label = f"{brand} — {model}" if brand else model
            findings.append({
                "kind": "finding",
                "state": "نمط عطل متكرر بين وحدات مماثلة",
                "subject": label,
                "comparison": f'نوع العطل «{fault_type}» ظهر لدى {distinct} وحدات مماثلة.',
                "evidence": "تم تجميع السجل حسب الطراز ونوع العطل، مع احتساب الوحدات المختلفة لا عدد البلاغات فقط.",
                "meaning": "يوجد نمط متكرر يستحق مراجعة تفاصيل الأعطال والإصلاحات؛ لا يثبت وجود سبب مشترك.",
            })

    linked = [r for r in rows if r["distance_km"] and r["distance_km"] > 0]
    if linked:
        mission_linked = [r for r in linked if r["mission_distance_km"] and r["mission_distance_km"] > 0]
        if mission_linked:
            findings.append({
                "kind": "context",
                "state": "الاستخدام الفعلي قابل للربط",
                "subject": "الحضيرة",
                "comparison": "توجد وحدات لها مسافة عداد ومهمات مكتملة بالعداد ضمن البيانات المتاحة.",
                "evidence": f'{len(mission_linked)} وحدات لها مسافة مقاسة ومسافة مهمات قابلة للمقارنة.',
                "meaning": "يمكن استخدام هذا الربط لاحقًا لفحص اتساق سجل المهمات مع الاستخدام الفعلي دون اعتبار الاختلاف وحده خطأ.",
            })

    if totals["maintenance_records"] and totals["faults"]:
        findings.append({
            "kind": "context",
            "state": "الصيانة والأعطال قابلة للمقارنة",
            "subject": "الحضيرة",
            "comparison": "توجد سجلات من المصدرين في الفترة الحالية للبيانات.",
            "evidence": f'{totals["maintenance_records"]} صيانة مقابل {totals["faults"]} أعطال.',
            "meaning": "تتوفر قاعدة لقراءة النشاط الوقائي والتصحيحي معًا؛ لا يمكن من هذه الأعداد وحدها إثبات أثر الصيانة على الأعطال.",
        })

    context = [f for f in findings if f.get("kind") == "context"]
    findings = [f for f in findings if f.get("kind") != "context"]
    return {"rows": rows, "totals": totals, "findings": findings, "context": context}


