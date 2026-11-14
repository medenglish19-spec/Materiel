"""
core/permissions.py
--------------------
نظام صلاحيات بسيط قائم على الأدوار (Role-Based Access Control).

في هذه المرحلة (الأساس) الأدوار ثابتة بالكود، وهذا كافٍ للبداية والاختبار.
لاحقًا يمكن تطويره لجدول roles/permissions ديناميكي بقاعدة البيانات دون
تغيير طريقة استخدامه في بقية الوحدات (لأن كل الوحدات تستدعي `require_role`
أو `require_permission` فقط، ولا تتعامل مع منطق الصلاحيات مباشرة).
"""

from enum import Enum
from fastapi import Depends, HTTPException, status

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.modules.users.models import User


class Role(str, Enum):
    ADMIN = "admin"           # صلاحية كاملة، إدارة المستخدمين
    FLEET_MANAGER = "fleet_manager"  # إدارة العتاد، الصيانة، المهمات
    OPERATOR = "operator"     # إدخال بيانات يومية (وقود، أعطال...)
    VIEWER = "viewer"         # اطّلاع فقط، بدون تعديل


# ترتيب الصلاحية من الأعلى للأدنى (يُستخدم لو احتجنا "على الأقل هذا المستوى")
ROLE_HIERARCHY = {
    Role.ADMIN: 4,
    Role.FLEET_MANAGER: 3,
    Role.OPERATOR: 2,
    Role.VIEWER: 1,
}


def require_role(*allowed_roles: Role):
    """
    Dependency تُستخدم في أي router:
        @router.post(..., dependencies=[Depends(require_role(Role.ADMIN))])
    """

    def checker(current_user: User = Depends(get_current_user)) -> User:
        # تعطيل مؤقت لاشتراط الصلاحية (انظر app/core/config.py).
        # عند إعادة المصادقة: DEV_DISABLE_AUTH=false فتعود هذه الفحوص كما كانت.
        if settings.DEV_DISABLE_AUTH:
            return current_user
        if current_user.role not in [r.value for r in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ليست لديك صلاحية للقيام بهذا الإجراء",
            )
        return current_user

    return checker


def require_min_role(min_role: Role):
    """نسخة بديلة: يسمح لأي دور مستواه >= الدور المطلوب."""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        # تعطيل مؤقت لاشتراط الصلاحية (انظر app/core/config.py).
        if settings.DEV_DISABLE_AUTH:
            return current_user
        user_level = ROLE_HIERARCHY.get(Role(current_user.role), 0)
        required_level = ROLE_HIERARCHY[min_role]
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ليست لديك صلاحية للقيام بهذا الإجراء",
            )
        return current_user

    return checker
