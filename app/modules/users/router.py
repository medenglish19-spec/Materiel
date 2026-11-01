"""
modules/users/router.py
--------------------------
طبقة الربط فقط: تستقبل الطلبات، تستدعي services، وترجع الاستجابة. لا يوجد
هنا أي منطق عمل (لا تشفير، لا استعلامات SQL مباشرة).

يحتوي:
- صفحة/نقطة تسجيل الدخول (تضع كوكي الجلسة)
- تسجيل الخروج
- صفحة إدارة المستخدمين
- API لإدارة المستخدمين (خاص بالـ admin فقط)
"""

import ipaddress
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_ADMIN_PASSWORD, settings
from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.security import create_access_token
from app.core.templating import get_module_templates
from app.database.init_db import (
    admin_setup_required,
    admin_setup_requires_password_change,
    complete_admin_setup,
)
from app.database.session import get_db
from app.modules.users import services
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter()
templates = get_module_templates("app/modules/users/templates")


def _require_local_first_run(request: Request) -> None:
    client = request.client
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="المسار غير موجود")
    try:
        address = client.host.split("%", 1)[0]
        is_loopback = ipaddress.ip_address(address).is_loopback
    except ValueError:
        is_loopback = False
    origin = request.headers.get("origin") or request.headers.get("referer")
    if request.method == "POST" and not origin:
        is_loopback = False
    if origin:
        parsed_origin = urlsplit(origin)
        hostname = (parsed_origin.hostname or "").lower()
        try:
            origin_is_loopback = hostname == "localhost" or ipaddress.ip_address(
                hostname.split("%", 1)[0]
            ).is_loopback
        except ValueError:
            origin_is_loopback = False
        is_loopback = (
            is_loopback
            and origin_is_loopback
            and parsed_origin.netloc.lower() == request.url.netloc.lower()
        )
    if not is_loopback:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="المسار غير موجود")


# ---------------------------------------------------------------
# صفحات الواجهة (تسجيل الدخول / الخروج / المستخدمون)
# ---------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if admin_setup_required():
        return RedirectResponse(url="/setup", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
            "password_changed": request.query_params.get("password_changed") == "1",
            "setup_required": False,
        },
    )


@router.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    if admin_setup_required():
        return RedirectResponse(url="/setup", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user = services.authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "اسم المستخدم أو كلمة المرور غير صحيحة",
                "password_changed": False,
                "setup_required": False,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_access_token({"sub": user.username, "role": user.role})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    _require_local_first_run(request)
    if not admin_setup_required():
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
            "password_changed": False,
            "setup_required": True,
            "setup_change_default_password": admin_setup_requires_password_change(),
        },
    )


@router.post("/setup")
def setup_admin(
    request: Request,
    password: str = Form(...),
    confirmation: str = Form(...),
    db: Session = Depends(get_db),
):
    _require_local_first_run(request)
    if not admin_setup_required():
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    error = None
    if len(password) < 12:
        error = "يجب أن تتكون كلمة المرور من 12 خانة على الأقل."
    elif len(password.encode("utf-8")) > 72:
        error = "كلمة المرور طويلة جدًا؛ الحد الأقصى 72 بايتًا."
    elif password != confirmation:
        error = "تأكيد كلمة المرور غير مطابق."
    if error:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": error,
                "password_changed": False,
                "setup_required": True,
                "setup_change_default_password": admin_setup_requires_password_change(),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        if admin_setup_requires_password_change():
            user = services.get_user_by_username(db, "admin")
            if user is None:
                raise ValueError("تعذر العثور على حساب المدير الحالي؛ أعد تشغيل البرنامج أو راجع سجل الأخطاء.")
            services.change_own_password(
                db, user, DEFAULT_ADMIN_PASSWORD, password, confirmation
            )
        else:
            user = services.create_user(
                db,
                UserCreate(
                    username="admin",
                    full_name="مدير النظام",
                    password=password,
                    role=Role.ADMIN.value,
                ),
            )
    except ValueError as exc:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": str(exc),
                "password_changed": False,
                "setup_required": True,
                "setup_change_default_password": admin_setup_requires_password_change(),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except IntegrityError:
        db.rollback()
        existing_admin = services.get_user_by_username(db, "admin")
        if existing_admin is not None and not admin_setup_requires_password_change():
            complete_admin_setup()
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    complete_admin_setup()
    token = create_access_token({"sub": user.username, "role": user.role})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={"users": services.list_users(db), "user": current_user},
    )


@router.post("/users/password")
def change_own_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirmation: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    try:
        services.change_own_password(
            db, current_user, current_password, new_password, confirmation
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    response = RedirectResponse("/login?password_changed=1", status_code=303)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response


# ---------------------------------------------------------------
# API إدارة المستخدمين (admin فقط)
# ---------------------------------------------------------------


@router.get("/api/users", response_model=list[UserOut])
def api_list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.ADMIN)),
):
    return services.list_users(db)


@router.post("/api/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def api_create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.ADMIN)),
):
    try:
        return services.create_user(db, user_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/api/users/{user_id}", response_model=UserOut)
def api_update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.ADMIN)),
):
    user = services.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    return services.update_user(db, user, user_in)


@router.get("/api/me", response_model=UserOut)
def api_me(current_user: User = Depends(get_current_user)):
    return current_user
