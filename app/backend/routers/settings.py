import json
from copy import deepcopy
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..audit import log as audit_log
from ..business_scope import business_id_from_area_focus, normalize_business_id_param, visible_business_id
from ..data_fetch_service import (
    DataFetchConfigError,
    DataFetchPlanError,
    _preferred_date_column,
    calculation_query_text,
    load_catalog,
    plan_with_default_calculation,
)
from ..deps import get_current_user, get_db, require_view_access
from ..models import Business, User
from ..productivity_finance_process_check import build_productivity_finance_process_check
from ..schemas import (
    AppSettingsOut,
    AppSettingsUpdate,
    ProductivityFinanceCalculationTestOut,
    ProductivityFinanceCalculationTestRequest,
    ProductivityFinanceProcessCheckRequest,
    ProductivityFinanceSettingsOut,
    ProductivityFinanceSettingsUpdate,
    RoleViewAccessOut,
    RoleViewAccessUpdate,
    SidebarLayoutOut,
    SidebarLayoutUpdate,
    StaffingSettingsOut,
    StaffingSettingsUpdate,
)
from ..settings_service import (
    LOCK_FOREIGN_SCHEDULE_CELLS_KEY,
    ROLE_VIEW_ACCESS_KEY,
    SIDEBAR_LAYOUT_KEY,
    STAFFING_HISTORY_HOURS_MAX,
    STAFFING_HISTORY_HOURS_MIN,
    PRODUCTIVITY_FINANCE_AMOUNT_MAX,
    PRODUCTIVITY_FINANCE_AMOUNT_MIN,
    PRODUCTIVITY_FINANCE_KEY,
    clean_productivity_finance_company_code,
    get_lock_foreign_schedule_cells,
    get_productivity_finance_settings,
    get_role_view_access,
    get_sidebar_layout,
    get_staffing_activity_capacity_activity_ids,
    get_staffing_history_hours,
    productivity_finance_invoice_rows_for_company,
    productivity_finance_vas_rates_from_invoice_rows,
    set_role_view_access,
    set_lock_foreign_schedule_cells,
    set_productivity_finance_settings,
    set_sidebar_layout,
    set_staffing_activity_capacity_activity_ids,
    set_staffing_history_hours,
)
from ..user_access import ROLE_ACCESS_LEVEL_RANK, ROLE_VIEW_IDS, ROLE_VIEW_ROLES, feature_registry_payload, normalize_role_view_id
from .data_fetch import _business_tenant, _fetch_rows, _plan_from_prompt, compute_calculation

router = APIRouter(prefix="/api/settings", tags=["settings"])

ROLE_VIEW_ACCESS_ROLES = ROLE_VIEW_ROLES
ROLE_VIEW_ACCESS_VIEWS = ROLE_VIEW_IDS
ROLE_VIEW_ACCESS_LEVELS = set(ROLE_ACCESS_LEVEL_RANK)


def _settings_out(db: Session, business_id: int | None) -> AppSettingsOut:
    return AppSettingsOut(
        lock_foreign_schedule_cells=get_lock_foreign_schedule_cells(db, business_id=business_id),
    )


def _sidebar_layout_out(db: Session, business_id: int | None) -> SidebarLayoutOut:
    return SidebarLayoutOut(items=get_sidebar_layout(db, business_id=business_id))


def _role_view_access_out(db: Session, business_id: int | None) -> RoleViewAccessOut:
    return RoleViewAccessOut(access=get_role_view_access(db))


def _staffing_settings_out(db: Session, business_id: int | None) -> StaffingSettingsOut:
    return StaffingSettingsOut(
        history_hours=get_staffing_history_hours(db, business_id=business_id),
        min_history_hours=STAFFING_HISTORY_HOURS_MIN,
        max_history_hours=STAFFING_HISTORY_HOURS_MAX,
        activity_capacity_activity_ids=get_staffing_activity_capacity_activity_ids(db, business_id=business_id),
    )


def _productivity_finance_company_codes(db: Session, business_id: int | None) -> list[str]:
    codes: set[str] = set()
    business = db.get(Business, business_id) if business_id is not None else None
    if business is not None:
        codes.update(clean_productivity_finance_company_code(code) for code in (business.company_codes or []))
    return sorted(code for code in codes if code)


def _productivity_finance_settings_out(db: Session, business_id: int | None) -> ProductivityFinanceSettingsOut:
    setting = get_productivity_finance_settings(db, business_id=business_id)
    company_codes = _productivity_finance_company_codes(db, business_id)
    allowed_company_codes = set(company_codes)
    stored_invoice_rows = setting.get("invoice_rows_by_company") or {}
    invoice_rows_by_company = {
        company: productivity_finance_invoice_rows_for_company(company, stored_invoice_rows.get(company))
        for company in company_codes
    }
    rates = {
        company: amount
        for company, amount in (setting.get("vas_hourly_revenue_by_company") or {}).items()
        if company in allowed_company_codes
    }
    for company, rows in invoice_rows_by_company.items():
        if company not in rates:
            rates[company] = productivity_finance_vas_rates_from_invoice_rows(rows)
    return ProductivityFinanceSettingsOut(
        hourly_cost=float(setting.get("hourly_cost") or 0.0),
        min_amount=PRODUCTIVITY_FINANCE_AMOUNT_MIN,
        max_amount=PRODUCTIVITY_FINANCE_AMOUNT_MAX,
        vas_hourly_revenue_by_company=rates,
        invoice_rows_by_company=invoice_rows_by_company,
        company_codes=company_codes,
    )


def _scoped_settings_business_id(
    db: Session,
    user: User,
    business_id: int | None,
    area_focus: str | None,
) -> int | None:
    business_id = normalize_business_id_param(business_id)
    if business_id is not None:
        return visible_business_id(db, user, business_id)
    focus_business_id = business_id_from_area_focus(db, area_focus)
    if focus_business_id is not None:
        return visible_business_id(db, user, focus_business_id)
    return visible_business_id(db, user, business_id)


def _audit_setting_change(
    db: Session,
    *,
    key: str,
    action: str,
    old_value: dict,
    new_value: dict,
    user_id: int,
    business_id: int | None,
) -> None:
    if old_value == new_value:
        return
    audit_log(
        db,
        entity_type="app_setting",
        entity_id=0,
        action=action,
        old_value={"key": key, "value": old_value},
        new_value={"key": key, "value": new_value},
        user_id=user_id,
        business_id=business_id,
    )


def _month_test_prompt(prompt: str, *, year: int, month: int) -> str:
    month_name = [
        "januari",
        "februari",
        "mars",
        "april",
        "maj",
        "juni",
        "juli",
        "augusti",
        "september",
        "oktober",
        "november",
        "december",
    ][month - 1]
    return f"{prompt.strip()} under {month_name} {year}"


def _company_column_id_for_plan(plan: dict) -> str | None:
    try:
        view = load_catalog().view(str(plan.get("view") or ""))
    except DataFetchConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except DataFetchPlanError:
        return None

    for column_id in ("company", "company_code", "bolag"):
        if column_id in view.column_by_id:
            return column_id
    for column in view.columns:
        label = f"{column.id} {column.label_en} {column.label_sv}".strip().lower().replace("_", " ")
        if "bolag" in label or "company" in label:
            return column.id
    return None


def _calculation_plan_with_company_filter(plan: dict, company_code: object) -> dict:
    code = clean_productivity_finance_company_code(company_code)
    if not code:
        return plan
    company_column_id = _company_column_id_for_plan(plan)
    if not company_column_id:
        return plan
    filters = [
        item
        for item in (plan.get("filters") or [])
        if str(item.get("id") or item.get("field") or "") != company_column_id
    ]
    filters.append({"id": company_column_id, "operator": "EQ", "value": code})
    reason = str(plan.get("reason") or "").strip()
    suffix = f"Bolagsfilter {company_column_id}={code} lades pa automatiskt."
    return {**plan, "filters": filters, "reason": f"{reason} {suffix}".strip()}


def _calculation_sql_for_plan(plan: dict) -> str:
    return calculation_query_text(plan_with_default_calculation(plan, "count"))


def _calculation_plan_without_period_filter(plan: dict) -> dict:
    result = deepcopy(plan)
    try:
        view = load_catalog().view(str(result.get("view") or ""))
        date_column = _preferred_date_column(view)
    except (DataFetchConfigError, DataFetchPlanError):
        return result
    if date_column is None:
        return result
    result["filters"] = [
        item
        for item in (result.get("filters") or [])
        if not (
            (item.get("id") or item.get("field")) == date_column.id
            and str(item.get("operator") or "") == "Between"
        )
    ]
    return result


def _clean_sidebar_layout(payload: SidebarLayoutUpdate) -> list[dict]:
    seen: set[str] = set()
    cleaned: list[dict] = []
    for item in payload.items:
        item_id = normalize_role_view_id(item.id)
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        heading = item.heading.strip()[:80]
        parent_id = normalize_role_view_id(item.parent_id) if item.parent_id else None
        cleaned.append({
            "id": item_id,
            "heading": heading,
            "parent_id": parent_id if parent_id and parent_id != item_id else None,
        })

    ids = {item["id"] for item in cleaned}
    for item in cleaned:
        if item["parent_id"] not in ids:
            item["parent_id"] = None
    for item in cleaned:
        visited = {item["id"]}
        parent_id = item["parent_id"]
        while parent_id:
            if parent_id in visited:
                item["parent_id"] = None
                break
            visited.add(parent_id)
            parent = next((candidate for candidate in cleaned if candidate["id"] == parent_id), None)
            parent_id = parent["parent_id"] if parent else None
    return cleaned


def _clean_role_view_access(payload: RoleViewAccessUpdate) -> dict[str, dict[str, str]]:
    cleaned: dict[str, dict[str, str]] = {}
    for role, views in (payload.access or {}).items():
        role_key = role.strip()
        if role_key not in ROLE_VIEW_ACCESS_ROLES or not isinstance(views, dict):
            continue
        role_views: dict[str, str] = {}
        for view_id, level in views.items():
            view_key = normalize_role_view_id(view_id)
            level_key = level.strip()
            if view_key not in ROLE_VIEW_ACCESS_VIEWS or level_key not in ROLE_VIEW_ACCESS_LEVELS:
                continue
            role_views[view_key] = level_key
        cleaned[role_key] = role_views
    return cleaned


@router.get("", response_model=AppSettingsOut)
def get_app_settings(
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("appSettings", "view")),
) -> AppSettingsOut:
    scoped_business_id = _scoped_settings_business_id(db, user, business_id, area_focus)
    return _settings_out(db, scoped_business_id)


@router.put("", response_model=AppSettingsOut)
def update_app_settings(
    payload: AppSettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("appSettings", "edit")),
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
) -> AppSettingsOut:
    scoped_business_id = _scoped_settings_business_id(db, admin, business_id, area_focus)
    before = _settings_out(db, scoped_business_id).model_dump()
    set_lock_foreign_schedule_cells(
        db,
        payload.lock_foreign_schedule_cells,
        user_id=admin.id,
        business_id=scoped_business_id,
    )
    after = _settings_out(db, scoped_business_id).model_dump()
    _audit_setting_change(
        db,
        key=LOCK_FOREIGN_SCHEDULE_CELLS_KEY,
        action="update_lock",
        old_value=before,
        new_value=after,
        user_id=admin.id,
        business_id=scoped_business_id,
    )
    db.commit()
    return _settings_out(db, scoped_business_id)


@router.get("/staffing", response_model=StaffingSettingsOut)
def get_staffing_settings(
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("staffingSettings", "view")),
) -> StaffingSettingsOut:
    scoped_business_id = _scoped_settings_business_id(db, user, business_id, area_focus)
    return _staffing_settings_out(db, scoped_business_id)


@router.put("/staffing", response_model=StaffingSettingsOut)
def update_staffing_settings(
    payload: StaffingSettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("staffingSettings", "edit")),
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
) -> StaffingSettingsOut:
    scoped_business_id = _scoped_settings_business_id(db, admin, business_id, area_focus)
    before = _staffing_settings_out(db, scoped_business_id).model_dump()
    set_staffing_history_hours(
        db,
        float(payload.history_hours),
        user_id=admin.id,
        business_id=scoped_business_id,
    )
    if "activity_capacity_activity_ids" in payload.model_fields_set:
        set_staffing_activity_capacity_activity_ids(
            db,
            payload.activity_capacity_activity_ids,
            user_id=admin.id,
            business_id=scoped_business_id,
        )
    after = _staffing_settings_out(db, scoped_business_id).model_dump()
    _audit_setting_change(
        db,
        key="staffing_settings",
        action="update_staffing_settings",
        old_value=before,
        new_value=after,
        user_id=admin.id,
        business_id=scoped_business_id,
    )
    db.commit()
    return _staffing_settings_out(db, scoped_business_id)


@router.get("/productivity-finance", response_model=ProductivityFinanceSettingsOut)
def get_productivity_finance_settings_route(
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("productivityFinanceSettings", "view")),
) -> ProductivityFinanceSettingsOut:
    scoped_business_id = _scoped_settings_business_id(db, user, business_id, area_focus)
    return _productivity_finance_settings_out(db, scoped_business_id)


@router.put("/productivity-finance", response_model=ProductivityFinanceSettingsOut)
def update_productivity_finance_settings_route(
    payload: ProductivityFinanceSettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("productivityFinanceSettings", "edit")),
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
) -> ProductivityFinanceSettingsOut:
    scoped_business_id = _scoped_settings_business_id(db, admin, business_id, area_focus)
    before = _productivity_finance_settings_out(db, scoped_business_id).model_dump()
    allowed_company_codes = set(_productivity_finance_company_codes(db, scoped_business_id))
    update_payload = payload.model_dump()
    filtered_invoice_rows = {
        clean_productivity_finance_company_code(company): productivity_finance_invoice_rows_for_company(company, rows)
        for company, rows in update_payload.get("invoice_rows_by_company", {}).items()
        if clean_productivity_finance_company_code(company) in allowed_company_codes
    }
    filtered_rates = {
        clean_productivity_finance_company_code(company): amount
        for company, amount in update_payload.get("vas_hourly_revenue_by_company", {}).items()
        if clean_productivity_finance_company_code(company) in allowed_company_codes
    }
    for company, rows in filtered_invoice_rows.items():
        filtered_rates[company] = productivity_finance_vas_rates_from_invoice_rows(rows)
    update_payload["invoice_rows_by_company"] = filtered_invoice_rows
    update_payload["vas_hourly_revenue_by_company"] = filtered_rates
    set_productivity_finance_settings(
        db,
        update_payload,
        user_id=admin.id,
        business_id=scoped_business_id,
    )
    after = _productivity_finance_settings_out(db, scoped_business_id).model_dump()
    _audit_setting_change(
        db,
        key=PRODUCTIVITY_FINANCE_KEY,
        action="update_productivity_finance_settings",
        old_value=before,
        new_value=after,
        user_id=admin.id,
        business_id=scoped_business_id,
    )
    db.commit()
    return _productivity_finance_settings_out(db, scoped_business_id)


@router.post("/productivity-finance/calculation/test", response_model=ProductivityFinanceCalculationTestOut)
async def test_productivity_finance_calculation_route(
    payload: ProductivityFinanceCalculationTestRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("productivityFinanceSettings", "edit")),
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
) -> ProductivityFinanceCalculationTestOut:
    today = date.today()
    requested_business_id = business_id if business_id is not None else payload.business_id
    scoped_business_id = _scoped_settings_business_id(db, admin, requested_business_id, area_focus)
    company_code = clean_productivity_finance_company_code(payload.company_code)
    allowed_company_codes = set(_productivity_finance_company_codes(db, scoped_business_id))
    if company_code and company_code not in allowed_company_codes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bolaget ingar inte i vald verksamhet.")
    if payload.month > today.month:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Det går bara att testa månader som har startat i år.",
        )
    prompt = _month_test_prompt(payload.prompt, year=today.year, month=payload.month)
    plan = await _plan_from_prompt(prompt)
    if plan.get("status") == "needs_clarification":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=plan.get("question") or "Uträkningen behöver förtydligas.")
    plan = _calculation_plan_with_company_filter(plan, company_code)
    plan = plan_with_default_calculation(plan, "count")
    saved_plan = _calculation_plan_without_period_filter(plan)
    tenant = _business_tenant(db, scoped_business_id)
    rows = await run_in_threadpool(_fetch_rows, plan, "financecalc", tenant)
    calculation = await compute_calculation(plan, rows, "financecalc", tenant)
    value = calculation.get("value") if calculation else len(rows)
    if not isinstance(value, (int, float)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Uträkningen måste ge ett numeriskt värde.")
    calculation_sql = _calculation_sql_for_plan(saved_plan)
    return ProductivityFinanceCalculationTestOut(
        quantity=value,
        month=payload.month,
        year=today.year,
        plan=json.loads(json.dumps(saved_plan, ensure_ascii=False, default=str)),
        calculation_sql=calculation_sql,
        view=str(plan.get("view") or ""),
        view_label=str(plan.get("view_label") or plan.get("view") or ""),
    )


@router.post("/productivity-finance/process-check")
def check_productivity_finance_processes_route(
    payload: ProductivityFinanceProcessCheckRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("productivityFinanceSettings", "view")),
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
) -> dict:
    today = date.today()
    year = int(payload.year or today.year)
    if year > today.year or (year == today.year and payload.month > today.month):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Det går bara att kontrollera månader som har startat.",
        )
    scoped_business_id = _scoped_settings_business_id(db, user, business_id, area_focus)
    company_code = clean_productivity_finance_company_code(payload.company_code)
    allowed_company_codes = set(_productivity_finance_company_codes(db, scoped_business_id))
    if company_code and company_code not in allowed_company_codes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bolaget ingår inte i vald verksamhet.")
    business = db.get(Business, scoped_business_id) if scoped_business_id is not None else None
    result = build_productivity_finance_process_check(
        db,
        business=business,
        finance_settings=_productivity_finance_settings_out(db, scoped_business_id).model_dump(),
        month=payload.month,
        year=year,
        company_code=company_code or None,
        fetch_rows=_fetch_rows,
        tenant=_business_tenant(db, scoped_business_id),
        row_id=payload.row_id,
    )
    audit_log(
        db,
        entity_type="productivity_finance_process_check",
        entity_id=0,
        action="run",
        old_value=None,
        new_value={
            "period": result.get("period"),
            "company_codes": result.get("company_codes"),
            "row_id": result.get("target_row_id"),
            "summary": result.get("summary"),
        },
        user_id=user.id,
        business_id=scoped_business_id,
    )
    db.commit()
    return result


@router.get("/sidebar", response_model=SidebarLayoutOut)
def get_sidebar_settings(
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SidebarLayoutOut:
    scoped_business_id = _scoped_settings_business_id(db, user, business_id, area_focus)
    return _sidebar_layout_out(db, scoped_business_id)


@router.put("/sidebar", response_model=SidebarLayoutOut)
def update_sidebar_settings(
    payload: SidebarLayoutUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("sidebarLayout", "edit")),
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
) -> SidebarLayoutOut:
    scoped_business_id = _scoped_settings_business_id(db, admin, business_id, area_focus)
    before = {"items": get_sidebar_layout(db, business_id=scoped_business_id)}
    set_sidebar_layout(db, _clean_sidebar_layout(payload), user_id=admin.id, business_id=scoped_business_id)
    after = {"items": get_sidebar_layout(db, business_id=scoped_business_id)}
    _audit_setting_change(
        db,
        key=SIDEBAR_LAYOUT_KEY,
        action="update_sidebar_layout",
        old_value=before,
        new_value=after,
        user_id=admin.id,
        business_id=scoped_business_id,
    )
    db.commit()
    return _sidebar_layout_out(db, scoped_business_id)


@router.get("/role-access", response_model=RoleViewAccessOut)
def get_role_access_settings(
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RoleViewAccessOut:
    return _role_view_access_out(db, None)


@router.get("/feature-registry")
def get_feature_registry(
    user: User = Depends(get_current_user),
) -> dict:
    return feature_registry_payload()


@router.put("/role-access", response_model=RoleViewAccessOut)
def update_role_access_settings(
    payload: RoleViewAccessUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("roleAccess", "edit")),
    business_id: int | None = Query(None),
) -> RoleViewAccessOut:
    before = {"access": get_role_view_access(db)}
    set_role_view_access(db, _clean_role_view_access(payload), user_id=admin.id)
    after = {"access": get_role_view_access(db)}
    _audit_setting_change(
        db,
        key=ROLE_VIEW_ACCESS_KEY,
        action="update_role_access",
        old_value=before,
        new_value=after,
        user_id=admin.id,
        business_id=None,
    )
    db.commit()
    return _role_view_access_out(db, None)
