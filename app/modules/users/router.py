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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.security import create_access_token
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.users import services
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter()
templates = get_module_templates("app/modules/users/templates")

# ---------------------------------------------------------------
# صفحات الواجهة (تسجيل الدخول / الخروج / المستخدمون)
# ---------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@router.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user = services.authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "اسم المستخدم أو كلمة المرور غير صحيحة"},
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


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(Role.ADMIN)),
):
    return templates.TemplateResponse(
        "users.html", {"request": request, "users": services.list_users(db)}
    )


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
