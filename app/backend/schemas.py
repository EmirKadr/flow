from datetime import datetime

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


UserRole = Literal["admin", "leader", "staffing_manager", "viewer", "warehouse_clerk", "article_placer", "super_user"]


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    sort_order: int
    is_active: bool


class BusinessCreate(BaseModel):
    code: str
    name: str
    sort_order: int = 0
    is_active: bool = True


class BusinessUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class AreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    business_id: int | None = None
    code: str
    name: str
    sort_order: int
    is_active: bool


class AreaCreate(BaseModel):
    business_id: int | None = None
    code: str
    name: str
    sort_order: int = 0
    is_active: bool = True


class AreaUpdate(BaseModel):
    business_id: int | None = None
    code: str | None = None
    name: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    business_id: int | None = None
    code: str
    label: str
    area_id: int | None
    summary_activity_id: int | None
    color: str
    category: str
    sort_order: int
    is_active: bool
    required_competency: str | None


class ActivityCreate(BaseModel):
    business_id: int | None = None
    code: str | None = None
    label: str
    area_id: int | None = None
    summary_activity_id: int | None = None
    color: str = "#ffffff"
    category: str = "work"
    sort_order: int = 0
    required_competency: str | None = None


class ActivityUpdate(BaseModel):
    business_id: int | None = None
    code: str | None = None
    label: str | None = None
    area_id: int | None = None
    summary_activity_id: int | None = None
    color: str | None = None
    category: str | None = None
    sort_order: int | None = None
    required_competency: str | None = None


class ActivityImportError(BaseModel):
    row: int
    label: str | None = None
    error: str


class ActivityImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[ActivityImportError] = Field(default_factory=list)


class ActivityImportRowInput(BaseModel):
    business: str | int | float | None = None
    label: str | int | float | None = None
    area: str | int | float | None = None
    summary_activity: str | int | float | None = None
    sort_order: str | int | float | None = None


class ActivityImportRowsRequest(BaseModel):
    rows: list[ActivityImportRowInput] = Field(default_factory=list, max_length=500)


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    business_id: int | None = None
    name: str
    noman: str | None = None
    home_area_id: int | None
    home_activity_id: int | None = None
    competencies: list[str] = Field(default_factory=list)
    comment: str | None
    has_fixed_schedule: bool = True
    is_active: bool
    sort_order: int


class PersonCreate(BaseModel):
    business_id: int | None = None
    name: str
    noman: str | None = None
    home_area_id: int | None = None
    home_activity_id: int | None = None
    competencies: list[str] = Field(default_factory=list)
    comment: str | None = None
    has_fixed_schedule: bool = True
    is_active: bool = True
    sort_order: int = 0


class PersonUpdate(BaseModel):
    business_id: int | None = None
    name: str | None = None
    noman: str | None = None
    home_area_id: int | None = None
    home_activity_id: int | None = None
    competencies: list[str] | None = None
    comment: str | None = None
    has_fixed_schedule: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class PersonImportError(BaseModel):
    row: int
    name: str | None = None
    error: str


class PersonImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[PersonImportError] = Field(default_factory=list)


class PersonImportRowInput(BaseModel):
    business: str | int | float | None = None
    name: str | int | float | None = None
    noman: str | int | float | None = None
    home_area: str | int | float | None = None
    home_activity: str | int | float | None = None
    sort_order: str | int | float | None = None


class PersonImportRowsRequest(BaseModel):
    rows: list[PersonImportRowInput] = Field(default_factory=list, max_length=500)


class PersonSortOrderUpdate(BaseModel):
    person_ids: list[int] = Field(min_length=2, max_length=500)


class CellOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    person_id: int
    hour: int
    minute_start: int
    minute_end: int
    activity_id: int | None
    empty_override: bool = False
    version: int
    updated_at: datetime | None = None
    updated_by: int | None = None


class ScheduleOut(BaseModel):
    year: int
    week: int
    weekday: int
    area_id: int | None
    revision_key: str | None = None
    persons: list[PersonOut]
    cells: list[CellOut]
    scheduled_hours: dict[int, list[int]] = Field(default_factory=dict)  # person_id → [7,8,9,...]
    scheduled_defaults: dict[int, dict[int, int]] = Field(default_factory=dict)  # person_id → {hour → activity_id}
    lock_foreign_schedule_cells: bool = False


class CellUpdate(BaseModel):
    year: int
    week: int
    weekday: int
    hour: int
    minute_start: int = 0
    minute_end: int = 60
    person_id: int
    activity_id: int | None
    expected_version: int


class BulkCellItem(BaseModel):
    year: int
    week: int
    weekday: int
    hour: int
    minute_start: int = 0
    minute_end: int = 60
    person_id: int
    activity_id: int | None
    expected_version: int


class BulkCellRequest(BaseModel):
    cells: list[BulkCellItem]
    atomic: bool = True
    action: str = "drag_fill"


class RestoreSegment(BaseModel):
    minute_start: int
    minute_end: int
    activity_id: int | None
    empty_override: bool = False


class SegmentVersionRef(BaseModel):
    minute_start: int
    minute_end: int
    expected_version: int


class RestoreHourItem(BaseModel):
    year: int
    week: int
    weekday: int
    hour: int
    person_id: int
    expected_segments: list[SegmentVersionRef] = Field(default_factory=list)
    segments: list[RestoreSegment] = Field(default_factory=list)


class RestoreHoursRequest(BaseModel):
    hours: list[RestoreHourItem]
    action: str = "undo_restore"


class CellUpdateResponse(BaseModel):
    cell: CellOut


class ConflictResponse(BaseModel):
    error: str = "version_conflict"
    current: CellOut


class SummaryRow(BaseModel):
    activity_id: int
    activity_code: str
    activity_label: str
    color: str
    hours: float
    persons_equiv: float


class SplitCellRequest(BaseModel):
    year: int
    week: int
    weekday: int
    hour: int
    person_id: int
    segments: list[SegmentVersionRef] = Field(default_factory=list)
    merge_minute_start: int | None = None


class SplitCellResponse(BaseModel):
    segments: list[CellOut]


class CopyRequest(BaseModel):
    from_year: int
    from_week: int
    from_weekday: int | None = None
    to_year: int
    to_week: int
    to_weekday: int | None = None
    area_id: int | None = None
    overwrite: bool = False


class ClearRequest(BaseModel):
    year: int
    week: int
    weekday: int
    area_id: int | None = None
    person_id: int | None = None


class FillFromLeftRequest(BaseModel):
    year: int
    week: int
    weekday: int
    area_id: int | None = None


class LoginRequest(BaseModel):
    username: str
    password: str = ""


class PasswordSetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=72)


class TemplateDay(BaseModel):
    weekday: int = Field(ge=1, le=7)
    is_off: bool = False
    start_hour: int | None = None
    end_hour: int | None = None


class TemplateOut(BaseModel):
    person_id: int
    has_fixed_schedule: bool = True
    days: list[TemplateDay]


class TemplateUpdate(BaseModel):
    has_fixed_schedule: bool | None = None
    days: list[TemplateDay] = Field(default_factory=list)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str | None
    role: str
    roles: list[str] = Field(default_factory=list)
    business_id: int | None = None
    business_code: str | None = None
    business_name: str | None = None
    area_id: int | None = None
    must_change_password: bool = False
    is_super_user: bool = False
    is_demo: bool = False


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str | None
    role: str
    roles: list[str] = Field(default_factory=list)
    business_id: int | None = None
    business_code: str | None = None
    business_name: str | None = None
    area_id: int | None = None
    is_active: bool
    must_change_password: bool = False
    created_at: datetime
    is_super_user: bool = False
    is_demo: bool = False


class UserCreate(BaseModel):
    username: str
    password: str | None = Field(default=None, min_length=8, max_length=72)
    display_name: str | None = None
    role: UserRole = "leader"
    roles: list[UserRole] | None = None
    business_id: int | None = None
    area_id: int | None = None
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Användarnamn krävs")
        return cleaned

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("password", mode="before")
    @classmethod
    def normalize_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        roles = list(dict.fromkeys(value))
        if not roles:
            raise ValueError("Minst en roll krävs")
        return roles


class UserUpdate(BaseModel):
    username: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)
    display_name: str | None = None
    role: UserRole | None = None
    roles: list[UserRole] | None = None
    business_id: int | None = None
    area_id: int | None = None
    is_active: bool | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Användarnamn krävs")
        return cleaned

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        roles = list(dict.fromkeys(value))
        if not roles:
            raise ValueError("Minst en roll krävs")
        return roles


class UserImportError(BaseModel):
    row: int
    username: str | None = None
    error: str


class UserImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[UserImportError] = Field(default_factory=list)


class UserImportRowInput(BaseModel):
    business: str | int | float | None = None
    username: str | int | float | None = None
    display_name: str | int | float | None = None
    role: str | int | float | None = None
    roles: str | list[str] | None = None
    area: str | int | float | None = None


class UserImportRowsRequest(BaseModel):
    rows: list[UserImportRowInput] = Field(default_factory=list, max_length=500)


class AuditEntryOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    action: str
    old_value: dict | None = None
    new_value: dict | None = None
    user_id: int | None = None
    username: str | None = None
    display_name: str | None = None
    created_at: datetime


class AuditSummaryBucket(BaseModel):
    key: str
    label: str
    count: int


class AuditSummaryOut(BaseModel):
    total_events: int
    events_last_24h: int
    unique_users: int
    top_users: list[AuditSummaryBucket]
    top_actions: list[AuditSummaryBucket]
    top_entities: list[AuditSummaryBucket]


class AuditClientErrorIn(BaseModel):
    path: str = Field(max_length=300)
    method: str = Field(default="GET", max_length=10)
    status: int | None = Field(default=None, ge=0, le=599)
    error_code: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=500)
    detail: Any | None = None
    page_path: str | None = Field(default=None, max_length=300)


class AuditErrorEventOut(BaseModel):
    id: int
    created_at: datetime
    user_id: int | None = None
    username: str | None = None
    display_name: str | None = None
    entity_type: str
    entity_id: int
    action: str
    error_code: str
    error_type: str
    status_code: int | None = None
    path: str | None = None
    message: str | None = None


class AuditErrorSummaryOut(BaseModel):
    total_errors: int
    events_last_24h: int
    unique_users: int
    scanned_events: int
    truncated: bool = False
    top_error_codes: list[AuditSummaryBucket]
    top_actions: list[AuditSummaryBucket]
    top_paths: list[AuditSummaryBucket]
    top_users: list[AuditSummaryBucket]
    recent: list[AuditErrorEventOut]


class AppSettingsOut(BaseModel):
    lock_foreign_schedule_cells: bool = False


class AppSettingsUpdate(BaseModel):
    lock_foreign_schedule_cells: bool


class SidebarLayoutItem(BaseModel):
    id: str
    heading: str = ""
    parent_id: str | None = None


class SidebarLayoutOut(BaseModel):
    items: list[SidebarLayoutItem] = Field(default_factory=list)


class SidebarLayoutUpdate(BaseModel):
    items: list[SidebarLayoutItem] = Field(default_factory=list)


class RoleViewAccessOut(BaseModel):
    access: dict[str, dict[str, str]] = Field(default_factory=dict)


class RoleViewAccessUpdate(BaseModel):
    access: dict[str, dict[str, str]] = Field(default_factory=dict)
