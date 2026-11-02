"""
database/session.py
--------------------
مسؤول فقط عن: إنشاء Engine، وتوليد جلسة (Session) لكل طلب HTTP.

get_db() هو الـ Dependency الذي تستخدمه كل الوحدات (routers/services) للوصول
لقاعدة البيانات. هذا يضمن أن كل طلب يحصل على جلسة مستقلة تُغلق تلقائيًا بعد
انتهاء الطلب، بغض النظر عن نجاحه أو فشله.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import settings
from app.database import model_registry  # noqa: F401

IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")

# connect_args خاص بـ SQLite فقط (يسمح باستخدامه من أكثر من thread، وهو
# مطلوب مع FastAPI). لا يُستخدم مع PostgreSQL/MySQL.


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    """يجعل SQLite يطبّق المفاتيح الأجنبية فعلًا.

    SQLite لا يطبّقها افتراضيًا، ولهذا بقيت مئات الصفوف اليتيمة في القاعدة دون
    أن يكتشفها أحد: كل رابط لصف محذوف كُتب وقُبل بهدوء.

    ``PRAGMA foreign_keys`` مضبوط لكل اتصال لا للقاعدة، لذلك يُنفَّذ عند كل فتح
    اتصال. هذا مقصود: الـEngine يُبنى مرة واحدة، والاتصالات تأتي وتذهب مع كل
    طلب، والضبط في بناء الـEngine وحده لا يفيد شيئًا.

    التفعيل آمن الآن لأن stage13 وstage14 أزالا المخالفات التي كانت موجودة.
    تفعيله قبل ذلك كان سيفشل الإقلاع على قاعدة سليمة ظاهريًا.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _make_engine(url: str):
    """يبني Engine مع connect_args الخاص بـ SQLite وتفعيل المفاتيح الأجنبية.

    مستخرج كدالة لأن الاختبار يحتاج محركًا يشير إلى ملف مؤقت، وربطُه بالـEngine
    الوحدة فقط يجعل ذلك مستحيلًا دون تعديل الـsettings العام. ولهذا السبب نفسه
    سجّل الاستماع هنا لا في بناء الـEngine: أي محرك يُبنى من هنا يحصل على
    التفعيل، بمن فيهم محركو الاختبار.
    """
    is_sqlite = url.startswith("sqlite")
    args = {"check_same_thread": False, "timeout": 5} if is_sqlite else {}
    engine = create_engine(url, connect_args=args)
    if is_sqlite:
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


engine = _make_engine(settings.DATABASE_URL)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency تُستخدم في كل router:
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
