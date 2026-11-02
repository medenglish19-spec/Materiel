"""
core/security.py
-----------------
كل ما يخص التشفير والتوثيق (Authentication) بمكان واحد:
- تشفير/فحص كلمات المرور
- توليد وفحص JWT tokens

لا يجوز لأي وحدة (users, drivers...) تُنفّذ تشفير خاص بها. الكل يستدعي من هنا.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    if not plain_password:
        raise ValueError("كلمة المرور مطلوبة")
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password:
        return False
    if (
        pwd_context.identify(hashed_password) == "bcrypt"
        and len(plain_password.encode("utf-8")) > 72
    ):
        return False
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
