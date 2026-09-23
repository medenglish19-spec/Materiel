"""
database/session.py
--------------------
مسؤول فقط عن: إنشاء Engine، وتوليد جلسة (Session) لكل طلب HTTP.

get_db() هو الـ Dependency الذي تستخدمه كل الوحدات (routers/services) للوصول
لقاعدة البيانات. هذا يضمن أن كل طلب يحصل على جلسة مستقلة تُغلق تلقائيًا بعد
انتهاء الطلب، بغض النظر عن نجاحه أو فشله.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import settings

# connect_args خاص بـ SQLite فقط (يسمح باستخدامه من أكثر من thread، وهو
# مطلوب مع FastAPI). لا يُستخدم مع PostgreSQL/MySQL.
connect_args = (
    {"check_same_thread": False, "timeout": 5}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

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
