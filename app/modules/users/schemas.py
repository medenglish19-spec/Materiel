"""
modules/users/schemas.py
--------------------------
Pydantic schemas: تتحقق من شكل البيانات القادمة من الـ API/Forms، وتحدد
شكل البيانات الراجعة للمستخدم. الفصل بين UserCreate و UserOut مهم جدًا:
لا يجب أن ترجع كلمة المرور (حتى المشفّرة) في أي استجابة أبدًا.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


class UserBase(BaseModel):
    username: str
    full_name: str
    role: str = "viewer"

    @field_validator("username")
    @classmethod
    def username_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("اسم المستخدم مطلوب")
        return value


class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def password_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("كلمة المرور مطلوبة")
        return value

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        allowed = {"admin", "fleet_manager", "operator", "viewer"}
        if v not in allowed:
            raise ValueError(f"الدور يجب أن يكون أحد: {allowed}")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_must_not_be_empty_when_provided(cls, value: Optional[str]) -> Optional[str]:
        if value == "":
            raise ValueError("كلمة المرور مطلوبة")
        return value


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("اسم المستخدم مطلوب")
        return value

    @field_validator("password")
    @classmethod
    def password_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("كلمة المرور مطلوبة")
        return value
