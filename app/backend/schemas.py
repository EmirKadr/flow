from datetime import datetime

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


UserRole = Literal["admin", "leader", "staffing_manager", "viewer", "warehouse_clerk", "article_placer", "person", "super_user"]
PersonCollarType = Literal["blue_collar", "white_collar"]


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    company_codes: list[str] = Field(default_factory=list)
    tenant: str | None = None
    sort_order: int
    is_active: bool

    @field_validator("company_codes", mode="before")
    @classmethod
    def _default_company_codes(cls, value):
        return [] if value is None else value


class BusinessCreate(BaseModel):
    code: str | None = None
    name: str
    company_codes: list[str] = Field(default_factory=list)
    tenant: str | None = None
    sort_order: int = 0
    is_active: bool = True


class BusinessUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    company_codes: list[str] | None = None
    tenant: str | None = None
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
    code: str | None = None
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
    work_type: str = "normal"
    sort_order: int
    is_active: bool
    required_competency: str | None
    kpi_process_name: str | None = None


class ActivityKpiProcessOption(BaseModel):
    value: str
    label: str


class ActivityCreate(BaseModel):
    business_id: int | None = None
    code: str | None = None
    label: str
    area_id: int | None = None
    summary_activity_id: int | None = None
    color: str = "#ffffff"
    category: str = "work"
    work_type: str = "normal"
    sort_order: int = 0
    required_competency: str | None = None
    kpi_process_name: str | None = None


class ActivityUpdate(BaseModel):
    business_id: int | None = None
    code: str | None = None
    label: str | None = None
    area_id: int | None = None
    summary_activity_id: int | None = None
    color: str | None = None
    category: str | None = None
    work_type: str | None = None
    sort_order: int | None = None
    required_competency: str | None = None
    kpi_process_name: str | None = None


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
    kpi_process_name: str | int | float | None = None
    work_type: str | int | float | None = None
    sort_order: str | int | float | None = None


class ActivityImportRowsRequest(BaseModel):
    rows: list[ActivityImportRowInput] = Field(default_factory=list, max_length=500)


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    business_id: int | None = None
    name: str
    noman: str | None = None
    rfid_code: str | None = None
    collar_type: PersonCollarType = "blue_collar"
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
    rfid_code: str | None = None
    collar_type: PersonCollarType = "blue_collar"
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
    rfid_code: str | None = None
    collar_type: PersonCollarType | None = None
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
    rfid_code: str | int | float | None = None
    collar_type: str | int | float | None = None
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
    loan_area_id: int | None = None
    remark: str | None = None
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


class PresenceRow(BaseModel):
    person_id: int
    name: str
    home_area_id: int | None = None
    home_area: str | None = None
    current_activity_id: int | None = None
    current_activity: str
    current_activity_category: str | None = None


class PresenceBusinessGroup(BaseModel):
    business_id: int | None = None
    business_code: str
    business_name: str
    rows: list[PresenceRow] = Field(default_factory=list)


class PresenceOut(BaseModel):
    date: str
    year: int
    week: int
    weekday: int
    hour: int
    generated_at: datetime
    area_id: int | None = None
    groups: list[PresenceBusinessGroup] = Field(default_factory=list)


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


class CellRemarkUpdate(BaseModel):
    year: int
    week: int
    weekday: int
    hour: int
    minute_start: int = 0
    minute_end: int = 60
    person_id: int
    remark: str | None = Field(default=None, max_length=500)
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
    loan_area_id: int | None = None
    expected_version: int


class BulkCellRequest(BaseModel):
    cells: list[BulkCellItem]
    atomic: bool = True
    action: str = "drag_fill"


class RestoreSegment(BaseModel):
    minute_start: int
    minute_end: int
    activity_id: int | None
    loan_area_id: int | None = None
    remark: str | None = Field(default=None, max_length=500)
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


class SplitSegmentRange(BaseModel):
    minute_start: int
    minute_end: int


class SplitCellRequest(BaseModel):
    year: int
    week: int
    weekday: int
    hour: int
    person_id: int
    segments: list[SegmentVersionRef] = Field(default_factory=list)
    merge_minute_start: int | None = None
    split_minute: int = 30
    split_segments: list[SplitSegmentRange] = Field(default_factory=list)


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
    person_id: int | None = None
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
    person_id: int | None = None
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
    person_id: int | None = None
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
    person_id: int | None = None
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
    business_id: int | None = None
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
    trace_id: str | None = Field(default=None, max_length=32)


class AuditClientEventIn(BaseModel):
    event_type: str = Field(max_length=80)
    view_id: str | None = Field(default=None, max_length=80)
    view_label: str | None = Field(default=None, max_length=120)
    page_path: str | None = Field(default=None, max_length=300)


class AuditLocalRunIn(BaseModel):
    feature: str = Field(max_length=40)
    flow_id: str | None = Field(default=None, max_length=120)
    status: str = Field(default="ok", max_length=20)
    error_type: str | None = Field(default=None, max_length=120)
    duration_ms: int | None = Field(default=None, ge=0, le=60 * 60 * 1000)
    file_types: list[str] = Field(default_factory=list, max_length=40)
    row_counts: dict[str, int] = Field(default_factory=dict)
    result_counts: dict[str, int] = Field(default_factory=dict)


class InteractionEventIn(BaseModel):
    event_type: str = Field(max_length=80)
    view_id: str | None = Field(default=None, max_length=80)
    page_path: str | None = Field(default=None, max_length=300)
    control_id: str | None = Field(default=None, max_length=160)
    control_label: str | None = Field(default=None, max_length=180)
    control_role: str | None = Field(default=None, max_length=80)
    feature: str | None = Field(default=None, max_length=80)
    flow_id: str | None = Field(default=None, max_length=120)
    table_key: str | None = Field(default=None, max_length=120)
    table_label: str | None = Field(default=None, max_length=160)
    column_index: int | None = Field(default=None, ge=0, le=500)
    column_label: str | None = Field(default=None, max_length=180)
    row_count: int | None = Field(default=None, ge=0, le=10_000_000)
    client_surface: str | None = Field(default=None, max_length=40)
    interaction_id: str | None = Field(default=None, max_length=80)
    status: str = Field(default="ok", max_length=20)
    detail: dict | None = None


class InteractionEventBatchIn(BaseModel):
    items: list[InteractionEventIn] = Field(default_factory=list, max_length=100)


class InteractionEventOut(BaseModel):
    id: int
    created_at: datetime
    business_id: int | None = None
    user_id: int | None = None
    username: str | None = None
    display_name: str | None = None
    event_type: str
    view_id: str | None = None
    page_path: str | None = None
    control_id: str | None = None
    control_label: str | None = None
    control_role: str | None = None
    feature: str | None = None
    flow_id: str | None = None
    table_key: str | None = None
    table_label: str | None = None
    column_index: int | None = None
    column_label: str | None = None
    row_count: int | None = None
    client_surface: str | None = None
    interaction_id: str | None = None
    status: str
    detail: dict | None = None


class InteractionSummaryOut(BaseModel):
    total_events: int
    events_last_24h: int
    unique_users: int
    top_users: list[AuditSummaryBucket]
    top_views: list[AuditSummaryBucket]
    top_features: list[AuditSummaryBucket]
    top_controls: list[AuditSummaryBucket]
    top_flows: list[AuditSummaryBucket]
    top_columns: list[AuditSummaryBucket]
    top_surfaces: list[AuditSummaryBucket]
    copy_patterns: list[AuditSummaryBucket]
    recent: list[InteractionEventOut]


class InteractionCoverageOut(BaseModel):
    total_known_controls: int
    used_controls: int
    unused_controls: list[dict[str, str]]
    used_unknown_controls: list[AuditSummaryBucket]


class InteractionChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1600)
    period: str = Field(default="30d", max_length=20)
    business_id: int | None = None
    user_id: int | None = None
    q: str | None = Field(default=None, max_length=120)


class InteractionChatResponse(BaseModel):
    answer: str
    model: str
    event_count: int


class WaitMetricIn(BaseModel):
    event_type: str = Field(max_length=80)
    view_id: str | None = Field(default=None, max_length=80)
    target: str | None = Field(default=None, max_length=160)
    duration_ms: int = Field(ge=0, le=10 * 60 * 1000)
    status: str = Field(default="ok", max_length=20)
    detail: dict | None = None


class WaitMetricBatchIn(BaseModel):
    items: list[WaitMetricIn] = Field(default_factory=list, max_length=100)


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


class StaffingSettingsOut(BaseModel):
    history_hours: float = 40.0
    min_history_hours: float = 1.0
    max_history_hours: float = 240.0
    activity_capacity_activity_ids: list[int] | None = None


class StaffingSettingsUpdate(BaseModel):
    history_hours: float = Field(ge=1.0, le=240.0)
    activity_capacity_activity_ids: list[int] | None = None


class ProductivityFinanceVasRateAmounts(BaseModel):
    normal: float = 0.0
    ot_50: float = 0.0
    ob1_40: float = 0.0
    ob2_70: float = 0.0
    ob3_100: float = 0.0


class ProductivityFinanceCompanyRates(BaseModel):
    blue_collar: ProductivityFinanceVasRateAmounts = Field(default_factory=ProductivityFinanceVasRateAmounts)
    white_collar: ProductivityFinanceVasRateAmounts = Field(default_factory=ProductivityFinanceVasRateAmounts)


class ProductivityFinanceInvoiceRow(BaseModel):
    id: str
    section: str = ""
    service: str = ""
    description: str = ""
    unit: str = ""
    price: float = 0.0
    quantity: float = 0.0
    calculation_prompt: str = ""
    calculation_plan: dict[str, Any] | None = None
    calculation_sql: str = ""
    collar_type: PersonCollarType | None = None
    vas_rate_type: str | None = None
    linked_process_key: str | None = None
    linked_process_label: str | None = None


class ProductivityFinanceSettingsOut(BaseModel):
    hourly_cost: float = 0.0
    min_amount: float = 0.0
    max_amount: float = 10000000.0
    vas_hourly_revenue_by_company: dict[str, ProductivityFinanceCompanyRates] = Field(default_factory=dict)
    invoice_rows_by_company: dict[str, list[ProductivityFinanceInvoiceRow]] = Field(default_factory=dict)
    company_codes: list[str] = Field(default_factory=list)


class ProductivityFinanceSettingsUpdate(BaseModel):
    hourly_cost: float = Field(default=0.0, ge=0.0, le=10000000.0)
    vas_hourly_revenue_by_company: dict[str, Any] = Field(default_factory=dict)
    invoice_rows_by_company: dict[str, list[ProductivityFinanceInvoiceRow]] = Field(default_factory=dict)


class ProductivityFinanceCalculationTestRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    month: int = Field(ge=1, le=12)
    company_code: str | None = Field(default=None, max_length=40)
    business_id: int | None = None


class ProductivityFinanceCalculationTestOut(BaseModel):
    quantity: float
    month: int
    year: int
    plan: dict[str, Any]
    calculation_sql: str
    view: str
    view_label: str


class ProductivityFinanceProcessCheckRequest(BaseModel):
    month: int = Field(ge=1, le=12)
    year: int | None = Field(default=None, ge=2000, le=2100)
    company_code: str | None = Field(default=None, max_length=40)
    row_id: str | None = Field(default=None, max_length=120)


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


class PersonalPersonOut(BaseModel):
    id: int
    name: str
    noman: str | None = None
    business_id: int | None = None
    business_name: str | None = None
    home_area_id: int | None = None
    home_area: str | None = None


class PersonalActivityTotal(BaseModel):
    activity_id: int | None = None
    label: str
    color: str | None = None
    category: str | None = None
    minutes: int
    hours: float


class PersonalScheduleSegment(BaseModel):
    hour: int
    minute_start: int
    minute_end: int
    start: str
    end: str
    label: str
    activity_id: int | None = None
    color: str | None = None
    category: str | None = None
    source: str
    minutes: int


class PersonalScheduleDay(BaseModel):
    date: str
    weekday: int
    weekday_label: str
    status: str
    total_minutes: int
    work_minutes: int
    absence_minutes: int
    segments: list[PersonalScheduleSegment] = Field(default_factory=list)
    activities: list[PersonalActivityTotal] = Field(default_factory=list)


class PersonalWeekSummary(BaseModel):
    total_minutes: int
    work_minutes: int
    absence_minutes: int
    scheduled_days: int
    activities: list[PersonalActivityTotal] = Field(default_factory=list)


class PersonalProductivityPeriod(BaseModel):
    type: str
    label: str
    start_date: str
    end_date: str
    requested_days: int


class PersonalProductivityActivity(BaseModel):
    activity: str
    productivity_pct: float | None = None
    points_per_hour: float | None = None
    kpi_points: float = 0
    planned_kpi_points: float = 0
    kpi_minutes: int = 0
    kpi_hours: float = 0
    periods: int = 0
    event_count: int = 0
    diff_count: int = 0


class PersonalProductivityStatsSummary(BaseModel):
    days_with_data: int = 0
    days_with_activity: int = 0
    kpi_points: float = 0
    planned_kpi_points: float = 0
    productivity_pct: float | None = None
    points_per_hour: float | None = None
    kpi_minutes: int = 0
    kpi_hours: float = 0
    support_minutes: int = 0
    absence_minutes: int = 0
    event_count: int = 0
    diff_count: int = 0


class PersonalProductivityStats(BaseModel):
    status: str
    period: PersonalProductivityPeriod
    dates: list[str] = Field(default_factory=list)
    missing_dates: list[str] = Field(default_factory=list)
    source_status: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    activities: list[PersonalProductivityActivity] = Field(default_factory=list)
    summary: PersonalProductivityStatsSummary = Field(default_factory=PersonalProductivityStatsSummary)


class PersonalProductivityData(BaseModel):
    day: PersonalProductivityStats
    week: PersonalProductivityStats
    backfill: dict[str, Any] = Field(default_factory=dict)


class PersonalScheduleOut(BaseModel):
    year: int
    week: int
    person: PersonalPersonOut
    days: list[PersonalScheduleDay]
    summary: PersonalWeekSummary


class PersonalProductivityOut(BaseModel):
    date: str
    year: int
    week: int
    weekday: int
    person: PersonalPersonOut
    day: PersonalScheduleDay
    summary: PersonalWeekSummary
    productivity: PersonalProductivityData | None = None
