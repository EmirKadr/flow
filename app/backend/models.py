from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# JSONB on PostgreSQL (production), plain JSON on SQLite (local dev).
JsonField = JSON().with_variant(JSONB(), "postgresql")
BigIntId = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="leader")
    roles: Mapped[list[str] | None] = mapped_column(JsonField)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    business: Mapped["Business | None"] = relationship(back_populates="users")


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    users: Mapped[list[User]] = relationship(back_populates="business")
    areas: Mapped[list["Area"]] = relationship(back_populates="business")
    persons: Mapped[list["Person"]] = relationship(back_populates="business")
    activities: Mapped[list["Activity"]] = relationship(back_populates="business")


class Area(Base):
    __tablename__ = "areas"
    __table_args__ = (
        UniqueConstraint("business_id", "code", name="uq_areas_business_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    business: Mapped[Business | None] = relationship(back_populates="areas")
    persons: Mapped[list["Person"]] = relationship(back_populates="home_area")
    activities: Mapped[list["Activity"]] = relationship(back_populates="area")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    home_area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    home_activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    competencies: Mapped[list] = mapped_column(JsonField, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text)
    has_fixed_schedule: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    business: Mapped[Business | None] = relationship(back_populates="persons")
    home_area: Mapped[Area | None] = relationship(back_populates="persons")


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("business_id", "code", name="uq_activities_business_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    summary_activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#ffffff")
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="work")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    required_competency: Mapped[str | None] = mapped_column(String(40))

    business: Mapped[Business | None] = relationship(back_populates="activities")
    area: Mapped[Area | None] = relationship(back_populates="activities")


class ScheduleCell(Base):
    __tablename__ = "schedule_cells"
    __table_args__ = (
        UniqueConstraint("year", "week", "weekday", "hour", "person_id", "minute_start", name="uq_schedule_cell"),
        Index("ix_schedule_cells_ywd_person_hour", "year", "week", "weekday", "person_id", "hour"),
    )

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    minute_start: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    minute_end: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=60)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    empty_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class PersonScheduleTemplate(Base):
    __tablename__ = "person_schedule_templates"
    __table_args__ = (
        UniqueConstraint("person_id", "weekday", name="uq_person_schedule_weekday"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_hour: Mapped[int | None] = mapped_column(SmallInteger)
    end_hour: Mapped[int | None] = mapped_column(SmallInteger)
    is_off: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JsonField)
    new_value: Mapped[dict | None] = mapped_column(JsonField)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        UniqueConstraint("business_id", "key", name="uq_app_settings_business_key"),
    )

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
