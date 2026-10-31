"""
modules/users/services.py
----------------------------
كل منطق العمل الخاص بالمستخدمين: إنشاء مستخدم، تسجيل الدخول، تحديث بيانات.
الـ router يستدعي هذه الدوال فقط - لا يكتب أي استعلام SQL مباشر بنفسه.
"""

from typing import Optional
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserUpdate


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def list_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    return db.query(User).offset(skip).limit(limit).all()


def create_user(db: Session, user_in: UserCreate) -> User:
    if get_user_by_username(db, user_in.username):
        raise ValueError("اسم المستخدم موجود مسبقًا")

    user = User(
        username=user_in.username,
        full_name=user_in.full_name,
        role=user_in.role,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: User, user_in: UserUpdate) -> User:
    if user_in.full_name is not None:
        user.full_name = user_in.full_name
    if user_in.role is not None:
        user.role = user_in.role
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
    if user_in.password:
        user.hashed_password = hash_password(user_in.password)

    db.commit()
    db.refresh(user)
    return user


def change_own_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    confirmation: str,
) -> User:
    if not verify_password(current_password, user.hashed_password):
        raise ValueError("كلمة المرور الحالية غير صحيحة")
    if len(new_password) < 6:
        raise ValueError("كلمة المرور الجديدة يجب ألا تقل عن 6 خانات")
    if new_password != confirmation:
        raise ValueError("تأكيد كلمة المرور غير مطابق")
    if verify_password(new_password, user.hashed_password):
        raise ValueError("اختر كلمة مرور مختلفة عن الحالية")

    user.hashed_password = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """يرجع المستخدم لو صحّت بيانات الدخول، وإلا None."""
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
