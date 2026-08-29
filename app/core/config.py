"""
core/config.py
---------------
مصدر واحد لكل الإعدادات.
"""

import os
from functools import lru_cache


class Settings:
    APP_NAME: str = "Fleet & Assets Manager"
    ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = ENV != "production"

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./fleet_assets.db"
    )

    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "dev-only-secret-change-me-in-production"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )

    SESSION_COOKIE_NAME: str = "fleet_session"

    HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("APP_PORT", "8000"))

    # لا نستخدم Uvicorn reload تلقائيًا؛ إعادة تشغيل التطبيق تلقائيًا أثناء
    # startup كانت تجعل init_db/Alembic يعمل أكثر من مرة داخل Codespaces.
    UVICORN_RELOAD: bool = os.getenv("UVICORN_RELOAD", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
