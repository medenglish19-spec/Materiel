"""
modules/users/models.py
------------------------
تعريف بنية بيانات المستخدم فقط. لا يوجد هنا أي منطق (تشفير، تحقق...) -
هذا من مسؤولية services.py. الموديل يعرف "شكل البيانات" فقط.
"""

from sqlalchemy import Boolean, CheckConstraint, Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.shared.mixins import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(username) > 0", name="ck_users_username_nonempty"),
    )

    id = Column(Integer, primary_key=True, index=True)
    username = Column(Text, unique=True, index=True, nullable=False)
    full_name = Column(String(150), nullable=False)
    hashed_password = Column(String(255), nullable=False)

    # الدور يحدد الصلاحيات عبر core/permissions.py
    # القيم الممكنة: admin | fleet_manager | operator | viewer
    role = Column(String(30), nullable=False, default="viewer")

    is_active = Column(Boolean, default=True, nullable=False)
