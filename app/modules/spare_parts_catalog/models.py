from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class SparePartCategory(Base):
    __tablename__ = "spare_part_categories"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("spare_part_categories.id", ondelete="RESTRICT"), nullable=True, index=True)
    name_ar = Column(String(120), nullable=False)
    name_fr = Column(String(120), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    parent = relationship("SparePartCategory", remote_side=[id], back_populates="children")
    children = relationship("SparePartCategory", back_populates="parent")


class SparePartCatalogDetails(Base):
    __tablename__ = "spare_part_catalog_details"
    __table_args__ = (UniqueConstraint("spare_part_id", name="uq_spare_part_catalog_details_spare_part_id"),)

    id = Column(Integer, primary_key=True)
    spare_part_id = Column(Integer, ForeignKey("spare_parts.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("spare_part_categories.id", ondelete="RESTRICT"), nullable=True, index=True)
    name_ar = Column(String(160), nullable=True)
    name_fr = Column(String(160), nullable=True)
    original_name = Column(String(255), nullable=True)
    manufacturer = Column(String(160), nullable=True, index=True)
    source = Column(String(255), nullable=True)
    image_path = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    spare_part = relationship("SparePart")
    category = relationship("SparePartCategory")


class SparePartCatalogReference(Base):
    __tablename__ = "spare_part_catalog_references"
    __table_args__ = (Index("ix_spare_part_catalog_ref_lookup", "manufacturer", "reference"),)

    id = Column(Integer, primary_key=True)
    spare_part_id = Column(Integer, ForeignKey("spare_parts.id", ondelete="CASCADE"), nullable=False, index=True)
    manufacturer = Column(String(160), nullable=True)
    reference = Column(String(120), nullable=False)
    reference_type = Column(String(40), nullable=False, default="manufacturer", server_default="manufacturer")
    source = Column(String(255), nullable=True)

    spare_part = relationship("SparePart")


class SparePartCatalogModel(Base):
    """Equipment models that a catalog spare part fits."""
    __tablename__ = "spare_part_catalog_models"
    __table_args__ = (UniqueConstraint("spare_part_id", "equipment_model_id", name="uq_spare_part_catalog_model"),)

    id = Column(Integer, primary_key=True)
    spare_part_id = Column(Integer, ForeignKey("spare_parts.id", ondelete="CASCADE"), nullable=False, index=True)
    equipment_model_id = Column(Integer, ForeignKey("equipment_models.id", ondelete="CASCADE"), nullable=False, index=True)

    spare_part = relationship("SparePart")
    equipment_model = relationship("EquipmentModel")


class SparePartCatalogImport(Base):
    __tablename__ = "spare_part_catalog_imports"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    content_sha256 = Column(String(64), nullable=False, index=True)
    file_type = Column(String(16), nullable=False)
    status = Column(String(20), nullable=False, default="preview", server_default="preview", index=True)
    payload = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
