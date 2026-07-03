from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Float,
    Index,
    Integer,
    LargeBinary,
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
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    business: Mapped["Business | None"] = relationship(back_populates="users")


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_codes: Mapped[list[str]] = mapped_column(JsonField, nullable=False, default=list)
    tenant: Mapped[str | None] = mapped_column(String(80))
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
    __table_args__ = (
        UniqueConstraint("business_id", "rfid_code", name="uq_persons_business_rfid_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    noman: Mapped[str | None] = mapped_column(String(120))
    rfid_code: Mapped[str | None] = mapped_column(String(120))
    collar_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="blue_collar",
        server_default="blue_collar",
    )
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
    work_type: Mapped[str] = mapped_column(String(20), nullable=False, default="normal", server_default="normal")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    required_competency: Mapped[str | None] = mapped_column(String(40))
    kpi_process_name: Mapped[str | None] = mapped_column(String(255))

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
    loan_area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"))
    remark: Mapped[str | None] = mapped_column(Text)
    empty_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class RfidDevice(Base):
    __tablename__ = "rfid_devices"
    __table_args__ = (
        Index("ix_rfid_devices_business_activity", "business_id", "activity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    device_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    module_name: Mapped[str] = mapped_column(String(120), nullable=False)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    business: Mapped[Business | None] = relationship()
    activity: Mapped[Activity | None] = relationship()


class RfidScanEvent(Base):
    __tablename__ = "rfid_scan_events"
    __table_args__ = (
        Index("ix_rfid_scan_events_scan_time", "scan_time"),
        Index("ix_rfid_scan_events_business_scan_time", "business_id", "scan_time"),
        Index("ix_rfid_scan_events_person_scan_time", "person_id", "scan_time"),
        Index("ix_rfid_scan_events_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("rfid_devices.id"))
    device_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    module_name: Mapped[str] = mapped_column(String(120), nullable=False)
    tag_code: Mapped[str] = mapped_column(String(120), nullable=False)
    tag_dec: Mapped[str | None] = mapped_column(String(120))
    scan_count: Mapped[int | None] = mapped_column(Integer)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"))
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    scan_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    status_reason: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ignored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ignored_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    schedule_year: Mapped[int | None] = mapped_column(SmallInteger)
    schedule_week: Mapped[int | None] = mapped_column(SmallInteger)
    schedule_weekday: Mapped[int | None] = mapped_column(SmallInteger)
    schedule_hour: Mapped[int | None] = mapped_column(SmallInteger)
    schedule_minute: Mapped[int | None] = mapped_column(SmallInteger)

    business: Mapped[Business | None] = relationship()
    device: Mapped[RfidDevice | None] = relationship()
    person: Mapped[Person | None] = relationship()
    activity: Mapped[Activity | None] = relationship()


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


class PersonProductivityDaily(Base):
    __tablename__ = "person_productivity_daily"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "snapshot_date",
            "person_id",
            "row_type",
            "item_key",
            "metric",
            name="uq_person_productivity_daily_row",
        ),
        Index("ix_person_productivity_daily_lookup", "business_id", "snapshot_date", "person_id", "row_type"),
        Index("ix_person_productivity_daily_process", "business_id", "process_key", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    row_type: Mapped[str] = mapped_column(String(20), nullable=False)
    item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    metric: Mapped[str] = mapped_column(String(40), nullable=False, default="points")
    unit: Mapped[str | None] = mapped_column(String(40))
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    activity_label: Mapped[str | None] = mapped_column(String(120))
    process_key: Mapped[str | None] = mapped_column(String(120))
    process_label: Mapped[str | None] = mapped_column(String(255))
    kind: Mapped[str | None] = mapped_column(String(20))
    start_minute: Mapped[int | None] = mapped_column(Integer)
    end_minute: Mapped[int | None] = mapped_column(Integer)
    kpi_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    planned_kpi_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    kpi_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    support_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    absence_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diff_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_snapshot_at: Mapped[str | None] = mapped_column(String(40))
    schedule_signature: Mapped[str | None] = mapped_column(String(120))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    business: Mapped[Business | None] = relationship()
    person: Mapped[Person] = relationship()
    activity: Mapped[Activity | None] = relationship()


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


class UserWaitMetric(Base):
    __tablename__ = "user_wait_metrics"
    __table_args__ = (
        Index("ix_user_wait_metrics_created_at", "created_at"),
        Index("ix_user_wait_metrics_business_created", "business_id", "created_at"),
        Index("ix_user_wait_metrics_user_created", "user_id", "created_at"),
        Index("ix_user_wait_metrics_event_created", "event_type", "created_at"),
        Index("ix_user_wait_metrics_view_target", "view_id", "target"),
    )

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    view_id: Mapped[str | None] = mapped_column(String(80))
    target: Mapped[str | None] = mapped_column(String(160))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    detail: Mapped[dict | None] = mapped_column(JsonField)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserInteractionEvent(Base):
    __tablename__ = "user_interaction_events"
    __table_args__ = (
        Index("ix_user_interaction_events_created_at", "created_at"),
        Index("ix_user_interaction_events_business_created", "business_id", "created_at"),
        Index("ix_user_interaction_events_user_created", "user_id", "created_at"),
        Index("ix_user_interaction_events_view_control", "view_id", "control_id"),
        Index("ix_user_interaction_events_feature_flow", "feature", "flow_id"),
        Index("ix_user_interaction_events_table_column", "table_key", "column_label"),
    )

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    view_id: Mapped[str | None] = mapped_column(String(80))
    page_path: Mapped[str | None] = mapped_column(String(300))
    control_id: Mapped[str | None] = mapped_column(String(160))
    control_label: Mapped[str | None] = mapped_column(String(180))
    control_role: Mapped[str | None] = mapped_column(String(80))
    feature: Mapped[str | None] = mapped_column(String(80))
    flow_id: Mapped[str | None] = mapped_column(String(120))
    table_key: Mapped[str | None] = mapped_column(String(120))
    table_label: Mapped[str | None] = mapped_column(String(160))
    column_index: Mapped[int | None] = mapped_column(Integer)
    column_label: Mapped[str | None] = mapped_column(String(180))
    row_count: Mapped[int | None] = mapped_column(Integer)
    client_surface: Mapped[str | None] = mapped_column(String(40))
    interaction_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    detail: Mapped[dict | None] = mapped_column(JsonField)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CoreDataFile(Base):
    __tablename__ = "coredata_files"
    __table_args__ = (
        UniqueConstraint("business_code", "file_type", name="uq_coredata_files_business_file_type"),
        Index("ix_coredata_files_business_code", "business_code"),
        Index("ix_coredata_files_file_type", "file_type"),
        Index("ix_coredata_files_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True)
    business_code: Mapped[str] = mapped_column(String(50), nullable=False)
    file_type: Mapped[str] = mapped_column(String(80), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="text/csv")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="upload")
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MetaMediaUpload(Base):
    __tablename__ = "meta_media_uploads"
    __table_args__ = (
        Index("ix_meta_media_uploads_batch_id", "batch_id"),
        Index("ix_meta_media_uploads_created_at", "created_at"),
        Index("ix_meta_media_uploads_status", "status"),
        Index("ux_meta_media_uploads_content_hash", "content_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # Bytena lagras i MediaStore (disk), inte i databasen.
    storage_backend: Mapped[str | None] = mapped_column(String(20))
    storage_key: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending_analysis")
    analysis: Mapped[dict | None] = mapped_column(JsonField)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="public_upload")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MetaShipmentObservation(Base):
    __tablename__ = "meta_shipment_observations"
    __table_args__ = (
        UniqueConstraint("media_upload_id", name="uq_meta_shipment_observations_media_upload"),
        Index("ix_meta_shipment_observations_status", "analysis_status"),
        Index("ix_meta_shipment_observations_video_hash", "video_hash"),
        Index("ux_meta_shipment_observations_record_hash", "record_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True)
    media_upload_id: Mapped[int] = mapped_column(ForeignKey("meta_media_uploads.id"), nullable=False)
    label_image_upload_id: Mapped[int | None] = mapped_column(ForeignKey("meta_media_uploads.id"))
    video_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label_image_hash: Mapped[str | None] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    order_number: Mapped[str | None] = mapped_column(String(80))
    shipment_number: Mapped[str | None] = mapped_column(String(120))
    username: Mapped[str | None] = mapped_column(String(120))
    customer_name: Mapped[str | None] = mapped_column(String(200))
    pallet_id: Mapped[str | None] = mapped_column(String(120))
    deviations: Mapped[list | None] = mapped_column(JsonField)
    uncertainty_notes: Mapped[str | None] = mapped_column(Text)
    label_frame_time_seconds: Mapped[str | None] = mapped_column(String(40))
    analysis_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending_analysis")
    analysis_error: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(String(120))
    llm_raw_response: Mapped[dict | None] = mapped_column(JsonField)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    media_upload: Mapped[MetaMediaUpload] = relationship(foreign_keys=[media_upload_id])
    label_image_upload: Mapped[MetaMediaUpload | None] = relationship(foreign_keys=[label_image_upload_id])


class AllocationUserFilterProfile(Base):
    __tablename__ = "allocation_user_filter_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    profile: Mapped[dict] = mapped_column(JsonField, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StaffingCalculatorProfile(Base):
    __tablename__ = "staffing_calculator_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    profile: Mapped[dict] = mapped_column(JsonField, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


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
