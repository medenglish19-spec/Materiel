from collections import defaultdict
from decimal import Decimal

def build_utilization_analysis(items, meter_readings, missions, fuel_records):
    def num(value):
        try:
            return Decimal(str(value)) if value is not None else None
        except Exception:
            return None

    by_id = {x.id: x for x in items}
    readings = defaultdict(list)
    missions_map = defaultdict(list)
    fuel_map = defaultdict(list)

    for x in meter_readings:
        if num(x.odometer) is not None:
            readings[x.equipment_id].append(x)
    for x in missions:
        missions_map[x.equipment_id].append(x)
    for x in fuel_records:
        fuel_map[x.equipment_id].append(x)

    rows = []
    total_distance = Decimal("0")
    total_mission_distance = Decimal("0")
    total_fuel = Decimal("0")
    meter_history_count = 0
    mission_count = 0
    fuel_count = 0

    for equipment_id, item in by_id.items():
        history = sorted(readings[equipment_id], key=lambda x: (x.reading_date, x.id))
        first, last = (history[0], history[-1]) if history else (None, None)
        distance = None
        if first and last:
            delta = num(last.odometer) - num(first.odometer)
            if delta >= 0:
                distance = delta
                total_distance += delta
                meter_history_count += 1

        mission_distance = Decimal("0")
        complete_missions = 0
        for mission in missions_map[equipment_id]:
            start, end = num(mission.departure_meter), num(mission.return_meter)
            if start is not None and end is not None and end >= start:
                mission_distance += end - start
                complete_missions += 1

        fuel = Decimal("0")
        local_fuel_count = 0
        if first and last:
            for record in fuel_map[equipment_id]:
                if first.reading_date.date() <= record.fueling_date <= last.reading_date.date():
                    q = num(record.quantity)
                    if q is not None and q >= 0:
                        fuel += q
                        local_fuel_count += 1

        total_mission_distance += mission_distance
        mission_count += complete_missions
        total_fuel += fuel
        fuel_count += local_fuel_count

        rows.append({
            "equipment_id": equipment_id,
            "registration_number": item.registration_number,
            "model": item.equipment_model.name if item.equipment_model else "بدون طراز",
            "type": item.equipment_type.name if item.equipment_type else "بدون نوع",
            "distance_km": distance,
            "reading_count": len(history),
            "mission_count": len(missions_map[equipment_id]),
            "mission_distance_km": mission_distance,
            "fuel_liters": fuel,
            "fuel_records": local_fuel_count,
            "fuel_per_100km": (fuel / distance * 100) if distance and distance > 0 and local_fuel_count else None,
        })

    total_efficiency = (total_fuel / total_distance * 100) if total_distance > 0 and total_fuel > 0 else None
    findings = []
    if meter_history_count:
        findings.append({
            "state": "استخدام مقاس بالعداد",
            "subject": "الحضيرة",
            "evidence": f"{meter_history_count} وحدة لها تاريخ عداد يقيس {total_distance:.1f} كم.",
            "meaning": "المسافة مستخرجة من تطور قراءات العداد.",
        })
    if mission_count and total_distance > 0:
        gap = total_mission_distance - total_distance
        findings.append({
            "state": "اتساق سجل المهمات",
            "subject": "الحضيرة",
            "evidence": f"مسافات المهمات المكتملة بالعداد: {total_mission_distance:.1f} كم مقابل {total_distance:.1f} كم من قراءات العداد.",
            "meaning": f"الفارق {gap:.1f} كم؛ مؤشر لفحص اكتمال وربط السجلات، وليس إثباتا لخطأ.",
        })
    if total_efficiency is not None:
        findings.append({
            "state": "استهلاك وقود قابل للربط",
            "subject": "الحضيرة",
            "evidence": f"متوسط الوقود داخل فترة قراءات العداد: {total_efficiency:.2f} لتر/100 كم.",
            "meaning": "يستخدم كمؤشر استغلال ويحتاج مقارنة داخل النوع أو الطراز وفترة مماثلة.",
        })

    return {
        "rows": rows,
        "totals": {
            "equipment_with_meter_history": meter_history_count,
            "distance_km": total_distance,
            "mission_distance_km": total_mission_distance,
            "mission_count": mission_count,
            "fuel_liters": total_fuel,
            "fuel_records": fuel_count,
            "fuel_per_100km": total_efficiency,
        },
        "findings": findings,
    }
