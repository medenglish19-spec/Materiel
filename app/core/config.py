"""
core/config.py
---------------
مصدر واحد لكل الإعدادات.
"""

import os
import sys
from functools import lru_cache
from pathlib import Path
from sqlalchemy.engine import make_url


DEFAULT_SECRET_KEY = "dev-only-secret-change-me-in-production"
DEFAULT_ADMIN_PASSWORD = "Admin@123"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def packaged_data_directory(executable: Path | None = None) -> Path:
    """Return the durable data location used by the installed Windows build."""
    override = os.getenv("MATERIEL_DATA_DIR")
    executable = (executable or Path(sys.executable)).resolve()
    if override and override.strip():
        directory = Path(os.path.expandvars(override.strip())).expanduser()
        return directory if directory.is_absolute() else executable.parent / directory

    location_file = executable.parent / "materiel-data-dir.txt"
    try:
        configured = location_file.read_text(encoding="utf-8").strip()
    except OSError:
        configured = ""
    if configured:
        directory = Path(os.path.expandvars(configured)).expanduser()
        return directory if directory.is_absolute() else executable.parent / directory

    program_data = os.getenv("PROGRAMDATA")
    if program_data:
        return Path(program_data) / "Materiel" / "data"
    if os.name == "nt":
        local_data = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local_data) / "Materiel" / "data"
    return Path.home() / ".local" / "share" / "materiel" / "data"


def default_database_url(project_root: Path = PROJECT_ROOT) -> str:
    """Keep the default operational database independent of the launch cwd."""
    if getattr(sys, "frozen", False):
        database_path = packaged_data_directory() / "fleet_assets.db"
        return f"sqlite:///{database_path.resolve().as_posix()}"
    return f"sqlite:///{(project_root / 'fleet_assets.db').resolve().as_posix()}"


def resolve_database_url(database_url: str, project_root: Path = PROJECT_ROOT) -> str:
    """Resolve relative SQLite paths from the repository, not the process cwd."""
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        return database_url
    if url.database == ":memory:" or url.database.startswith("file:"):
        return database_url
    path = Path(url.database)
    if path.is_absolute():
        return database_url
    resolved = (project_root / path).resolve().as_posix()
    return url.set(database=resolved).render_as_string(hide_password=False)


class Settings:
    APP_NAME: str = "تسيير ومحاسبة العتاد"
    ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = ENV != "production"

    DATABASE_URL: str = resolve_database_url(
        os.getenv("DATABASE_URL") or default_database_url()
    )

    SECRET_KEY: str = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )

    SESSION_COOKIE_NAME: str = "fleet_session"

    # ------------------------------------------------------------------
    # تعطيل مؤقت لاشتراط تسجيل الدخول — بيئة التطوير المحلية فقط.
    # ------------------------------------------------------------------
    # عند تفعيله (الافتراضي مؤقتاً):
    #   * `get_current_user` لا يرفض الطلب بلا جلسة (لا 401)، ويستخدم
    #     `DEV_AUTH_USERNAME` كدور احتياطي حتى لا تتعطّل الإجراءات التي
    #     تحتاج `current_user.id`؛
    #   * `require_role` / `require_min_role` لا تُرجع 403؛
    #   * الصفحة الرئيسية `/` تفتح لوحة القيادة مباشرة.
    #
    # نظام المصادقة نفسه (تسجيل الدخول/الخروج/المستخدمون/كلمات المرور)
    # لم يُحذف: أي كوكي جلسة صالح لا يزال يُحترم.
    #
    # لإعادة تفعيل المصادقة كاملة، شغّل الخادم بـ:
    #     $env:DEV_DISABLE_AUTH = "false"   # PowerShell
    # أو أضف DEV_DISABLE_AUTH=false إلى بيئة التشغيل. لا تُستخدم هذه
    # القيمة على أي جهاز يمكن الوصول إليه من الشبكة.
    DEV_DISABLE_AUTH: bool = os.getenv("DEV_DISABLE_AUTH", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    DEV_AUTH_USERNAME: str = os.getenv("DEV_AUTH_USERNAME", "admin")

    # Logging (طبقتك غير الحظري في app/core/logging.py)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv(
        "LOG_DIR",
        str(packaged_data_directory() / "logs") if getattr(sys, "frozen", False) else "logs",
    )

    # مربوط بالمضيف المحلي فقط أثناء التعطيل المؤقت للمصادقة.
    # استعادة قيمة "0.0.0.0" عند إعادة تفعيل المصادقة إن لزم النشر على الشبكة.
    HOST: str = os.getenv("APP_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("APP_PORT", "8000"))

    # لا نستخدم Uvicorn reload تلقائيًا؛ إعادة تشغيل التطبيق تلقائيًا أثناء
    # startup كانت تجعل init_db/Alembic يعمل أكثر من مرة داخل Codespaces.
    # عند تفعيله، يراقب المجلدات المحددة في UVICORN_RELOAD_DIRS.
    UVICORN_RELOAD: bool = os.getenv("UVICORN_RELOAD", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # مجلدات تراقبها Uvicorn عند تفعيل reload. الافتراضي يغطي كود Python،
    # القوالب، والملفات الثابتة. يمكن تجاوزها بمتغير بيئي مفصولة بفواصل.
    UVICORN_RELOAD_DIRS: list[str] = [
        d.strip() for d in os.getenv("UVICORN_RELOAD_DIRS", "app,web,static").split(",")
        if d.strip()
    ]


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
