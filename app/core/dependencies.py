"""
core/dependencies.py
---------------------
Dependencies عامة لحماية الصفحات وربط العملية بالمستخدم الحالي.
"""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import decode_access_token
from app.database.session import get_db


def _mark_request_actor(request: Request, user_id: int) -> None:
    """يسجّل من أنشأ قراءة العدّاد لهذا الطلب (يدعم منفذين حقيقيين)."""
    try:
        from app.modules.meter_readings.audit_events import set_request_actor
        path = request.url.path
        kind = 'excel' if path.endswith('/import-excel') else ('paste' if path.endswith('/bulk-create') else 'manual')
        set_request_actor(user_id, kind)
    except Exception:
        pass


def _dev_auth_current_user(request: Request, db: Session):
    """الدور الذي يعمل به التطبيق عند تعطيل تسجيل الدخول مؤقتاً.

    - يُحترم كوكي جلسة صالح إن وُجد، فلا يتغير سلوك من سجّل دخوله فعلاً.
    - وإلا يُرجع `DEV_AUTH_USERNAME` (افتراضياً `admin`)، ثم أي مستخدم فعّال.
    - يعيد مستخدماً حقيقياً من قاعدة البيانات لا كائناً وهمياً، لأن معظم
      المسارات تكتب `current_user.id` في أعمدة مرتبطة بمفتاح خارجي.
    """
    from app.modules.users.models import User
    from app.modules.users.services import get_user_by_username

    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        payload = decode_access_token(token)
        username = payload.get("sub") if payload else None
        if username:
            user = get_user_by_username(db, username)
            if user is not None and user.is_active:
                _mark_request_actor(request, user.id)
                return user

    user = get_user_by_username(db, settings.DEV_AUTH_USERNAME)
    if user is None or not user.is_active:
        user = (
            db.query(User)
            .filter(User.is_active.is_(True))
            .order_by(User.id.asc())
            .first()
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="تعطيل المصادقة مفعّل لكن لا يوجد أي مستخدم فعّال في قاعدة البيانات",
        )
    _mark_request_actor(request, user.id)
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)):
    # ------------------------------------------------------------------
    # تعطيل مؤقت لاشتراط تسجيل الدخول (انظر app/core/config.py).
    # لإعادة تفعيل المصادقة: DEV_DISABLE_AUTH=false
    # ------------------------------------------------------------------
    if settings.DEV_DISABLE_AUTH:
        return _dev_auth_current_user(request, db)

    from app.modules.users.services import get_user_by_username
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="غير مصرح لك - الرجاء تسجيل الدخول")
    if not token:
        raise credentials_exception
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise credentials_exception
    user = get_user_by_username(db, payload["sub"])
    if user is None or not user.is_active:
        raise credentials_exception
    try:
        from app.modules.meter_readings.audit_events import set_request_actor
        path = request.url.path
        kind = 'excel' if path.endswith('/import-excel') else ('paste' if path.endswith('/bulk-create') else 'manual')
        set_request_actor(user.id, kind)
    except Exception:
        pass
    return user


def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None
