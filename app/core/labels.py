"""
core/labels.py
--------------
مصدر واحد لتحويل مفاتيح القوائم (enums) إلى نصوص عربية.

قبل هذا الملف كانت كل صفحة تنسخ سلّم `if/elif` خاصاً بها، فأي تغيير في
التسمية كان يجب أن يُكرَّر في خمسة مواضع، وأي موضع يُنسى يعرض مفتاحاً
إنجليزياً داخل واجهة عربية. الآن:

    {{ label('operational', item.operational_status) }}

ولصفحات الجافاسكربت التي تحتاج التسمية، تُحقن الخريطة كاملة مرة واحدة:

    window.MATERIEL_LABELS = {{ LABELS | tojson }};

مبدأ التصميم: **قيمة غير معروفة تُعرض كما هي** (لا صفحة بيضاء ولا استثناء)،
وهو نفس سلوك النماذج Dictionaries السابقة `.get(k, k)`.

لا يستورد هذا الملف أي وحدة نطاق (modules) حتى يبقى `core` مستقلاً؛
اختبار `tests/test_labels.py` هو من يضمن أن كل مفتاح معرّف في
`schemas.py` له تسمية هنا.
"""

from typing import Dict, List, Optional


# الوضعية التشغيلية للعتاد (equipment/schemas.py :: OPERATIONAL_STATUSES)
OPERATIONAL_STATUS_LABELS: Dict[str, str] = {
    "available": "متاح",
    "in_mission": "في مهمة",
    "in_maintenance": "في الصيانة",
    "in_external_workshop": "في ورشة خارجية",
    "unavailable": "غير متاح",
}

# الحالة الفنية للعتاد (equipment/schemas.py :: TECHNICAL_CONDITIONS)
TECHNICAL_CONDITION_LABELS: Dict[str, str] = {
    "ready": "جاهز",
    "ready_restricted": "جاهز مع قيود",
    "broken": "عاطل",
}

# حالة العطل (faults_repairs/schemas.py :: FAULT_STATUSES)
FAULT_STATUS_LABELS: Dict[str, str] = {
    "open": "مفتوح",
    "diagnosing": "قيد التشخيص",
    "repairing": "قيد الإصلاح",
    "waiting_parts": "بانتظار قطع الغيار",
    "repaired": "تم الإصلاح",
    "closed": "مغلق",
}

# حالة التصليح (faults_repairs/schemas.py :: REPAIR_STATUSES)
REPAIR_STATUS_LABELS: Dict[str, str] = {
    "in_progress": "قيد الإصلاح",
    "completed": "تم الإصلاح",
    "cancelled": "ملغى",
}

# خطورة العطل (نفس التسميات المستعملة في <select> داخل faults.html)
SEVERITY_LABELS: Dict[str, str] = {
    "low": "منخفضة",
    "medium": "متوسطة",
    "high": "عالية",
    "critical": "حرجة",
}


LABELS: Dict[str, Dict[str, str]] = {
    "operational": OPERATIONAL_STATUS_LABELS,
    "technical": TECHNICAL_CONDITION_LABELS,
    "fault": FAULT_STATUS_LABELS,
    "repair": REPAIR_STATUS_LABELS,
    "severity": SEVERITY_LABELS,
}


def label(kind: str, value: Optional[str], default: Optional[str] = None) -> str:
    """تسمية عربية لمفتاح. قيمة مجهولة تُعاد كما هي ما لم يُمرَّر `default`."""
    if value is None:
        return default if default is not None else ""
    return LABELS.get(kind, {}).get(value, default if default is not None else value)


def label_options(kind: str) -> List[tuple]:
    """`[(value, text), ...]` لبناء قوائم `<option>` بنفس ترتيب العرض الحالي."""
    return list(LABELS.get(kind, {}).items())
