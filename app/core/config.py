"""
core/config.py
---------------
مصدر واحد لكل الإعدادات.
"""

import os
from functools import lru_cache


DEFAULT_SECRET_KEY = "dev-only-secret-change-me-in-production"
DEFAULT_ADMIN_PASSWORD = "Admin@123"


class Settings:
    APP_NAME: str = "Fleet & Assets Manager"
    ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = ENV != "production"

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./fleet_assets.db"
    )

    SECRET_KEY: str = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )

    SESSION_COOKIE_NAME: str = "fleet_session"

    # Logging (طبقتك غير الحظري في app/core/logging.py)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")

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


def security_warnings(db_path: str | None = None) -> list[str]:
    """إعدادات لا يجب أن تصل إلى الإنتاج. تُسجَّل عند الإقلاع، لا توقفه.

    قرار متعمَّد: التطبيق **لا يرفض** الإقلاع ولا يغيّر كلمة مرور المدير
    (بقرار المستخدم)، لكنه يكتب تحذيراً صريحاً في السجل حتى لا يمرّ دون
    انتباه. `SECRET_KEY` المبدئي يجعل أي جلسة قابلة للتزوير، وكلمة مرور
    `admin` المبدئية منشورة في README وفي تاريخ المستودع.

    الدالة للقراءة فقط: لا تكتب في القاعدة ولا تغيّر الإعدادات.
    """
    warnings: list[str] = []

    if settings.SECRET_KEY == DEFAULT_SECRET_KEY:
        warnings.append(
            "SECRET_KEY هو القيمة الافتراضية المعروفة. أي شخص يقرأ هذا الملف يستطيع "
            "تزوير جلسة الدخول. عيّن SECRET_KEY قبل النشر "
            "(وليس في الإنتاج فقط، فأي بيئة مشتركة تستخدم نفس المفتاح)."
        )

    if db_path is None:
        return warnings

    from pathlib import Path

    database_file = Path(db_path)
    if not database_file.exists() or database_file.stat().st_size == 0:
        # قاعدة جديدة: سيُنشأ `admin` بكلمة المرور الافتراضية عند أول إقلاع.
        warnings.append(
            f"قاعدة البيانات {database_file.name} جديدة/فارغة: سيُنشأ مستخدم "
            f"admin بكلمة المرور الافتراضية {DEFAULT_ADMIN_PASSWORD}. "
            "غيّرها فوراً عبر واجهة المستخدمين."
        )
        return warnings

    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(f"sqlite:///{database_file.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
        if "users" not in tables:
            return warnings
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT hashed_password FROM users WHERE username = 'admin'")
            ).fetchall()
    except Exception:  # pragma: no cover - لا نمنع الإقلاع بسبب فحص
        return warnings
    finally:
        engine.dispose()

    if not rows:
        return warnings

    # لا نكشف الهاش؛ نتحقق فقط من بقاء كلمة المرور الافتراضية.
    from app.core.security import verify_password

    try:
        still_default = verify_password(DEFAULT_ADMIN_PASSWORD, rows[0][0])
    except Exception:  # pragma: no cover - bcrypt غير متاح/هاش غير صالح
        return warnings

    if still_default:
        warnings.append(
            "مستخدم admin ما زال بكلمة المرور الافتراضية "
            f"({DEFAULT_ADMIN_PASSWORD})، وهي منشورة في README وفي تاريخ المستودع. "
            "غيّرها قبل النشر."
        )
    return warnings
