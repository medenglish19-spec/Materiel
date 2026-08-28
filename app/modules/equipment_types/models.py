from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.shared.mixins import TimestampMixin


class EquipmentCategory(Base, TimestampMixin):
    __tablename__ = "equipment_categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_equipment_category_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(30), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_system = Column(Boolean, nullable=False, default=True)

    equipment_types = relationship("EquipmentType", back_populates="category")


class EquipmentBrand(Base, TimestampMixin):
    __tablename__ = "equipment_brands"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    models = relationship("EquipmentModel", back_populates="brand")


class EquipmentType(Base, TimestampMixin):
    __tablename__ = "equipment_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), unique=True, nullable=False)
    measurement_unit = Column(String(10), nullable=False)
    category_id = Column(
        Integer,
        ForeignKey("equipment_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    category = relationship("EquipmentCategory", back_populates="equipment_types")
    models = relationship(
        "EquipmentModel", back_populates="equipment_type", cascade="all, delete-orphan"
    )


class EquipmentModel(Base, TimestampMixin):
    __tablename__ = "equipment_models"
    __table_args__ = (
        UniqueConstraint(
            "equipment_type_id",
            "brand_id",
            "name",
            name="uq_model_per_type_brand",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), nullable=False)
    equipment_type_id = Column(Integer, ForeignKey("equipment_types.id"), nullable=False)
    brand_id = Column(
        Integer,
        ForeignKey("equipment_brands.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    equipment_type = relationship("EquipmentType", back_populates="models")
    brand = relationship("EquipmentBrand", back_populates="models")
