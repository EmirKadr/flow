"""Bygget av Sankey Inbound-payloaden: grafnoder, länkar, spårning och summering."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable

from ..data_fetch_service import (
    PACKAGE_BASE_UNIT_LABEL,
    build_package_ladders,
    split_quantity_into_packages,
)
from ..productivity_kpi_rules import (
    SQL_REFERENCE_KPI_RULE_ROWS,
    normalize_process,
    parse_kpi_rule_rows,
    parse_kpi_targets,
)
from ..settings_service import clean_productivity_finance_company_code
from .cache import SANKEY_INBOUND_PAYLOAD_SCHEMA
from .common import (
    BUFFER_UPDATE_RECEIVE_TYPE,
    CLIENT_FILTER_PREBUILD_MAX_SOURCE_ROWS,
    CLIENT_FILTER_PREBUILD_MAX_VIEWS,
    EXCLUDED_RECEIVE_TYPES,
    OPEN_STATUS_LABELS,
    OUTBOUND_METRICS,
    PROCESS_DEFAULT_METRIC,
    PROCESS_LABELS,
    PROCESS_POINT_ALIASES,
    PickQueueEntry,
    ProcessVisit,
    TraceBranch,
    ZEROING_RECEIVE_TYPE,
)
from .rows import (
    _clean_text,
    _client_filter_period_specs,
    _client_filter_view_key,
    _company_allowed,
    _inbound_prices,
    _is_in_date_window,
    _normalize_pall,
    _normalize_type,
    _order_starts_with,
    _outbound_prices,
    _outbound_trace_row,
    _pall_aliases,
    _period_label,
    _purchase_line_key,
    _round_money,
    _round_qty,
    _row_company,
    _row_datetime,
    _row_id,
    _row_item,
    _row_number,
    _row_order_number,
    _row_pall,
    _row_parent_pick_pall,
    _row_pick_zone,
    _row_picked_qty,
    _row_purchase_line,
    _row_purchase_number,
    _row_text,
    _row_value,
    _row_warehouse,
)


def _build_outbound_sankey(
    *,
    pick_rows: list[dict[str, Any]],
    dispatch_rows: list[dict[str, Any]],
    alias_rows: list[dict[str, Any]],
    prices: dict[str, dict[str, float]],
    allowed_companies: set[str],
    view_company_filter: str,
    view_period_start: date,
    view_period_end: date,
    include_trace_details: bool = True,
) -> dict[str, Any]:
    target_companies = (
        {view_company_filter}
        if view_company_filter != "ALL"
        else {company for company in allowed_companies if company}
    )
    if not target_companies:
        row_companies = {_row_company(row) for row in pick_rows + dispatch_rows if _row_company(row)}
        target_companies = row_companies

    nodes: dict[str, dict] = {}
    links: dict[tuple[str, str, str], dict] = {}
    trace_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    summary: dict[str, float] = {
        "outbound_income": 0.0,
        "outbound_store_income": 0.0,
        "outbound_ecom_income": 0.0,
        "outbound_picked_orders": 0.0,
        "outbound_picked_rows": 0.0,
        "outbound_picked_pcs": 0.0,
        "outbound_full_pallets": 0.0,
        "outbound_loaded_pallets": 0.0,
    }
    company_summaries: dict[str, dict[str, Any]] = {}
    package_ladders = build_package_ladders(alias_rows)
    default_package_ladder = [(PACKAGE_BASE_UNIT_LABEL, 1)]

    def _row_in_view(row: dict[str, Any], company: str) -> bool:
        return (
            _row_company(row) == company
            and _is_in_date_window(row, view_period_start, view_period_end)
        )

    pick_rows_by_company: dict[str, list[dict[str, Any]]] = {company: [] for company in target_companies}
    dispatch_rows_by_company: dict[str, list[dict[str, Any]]] = {company: [] for company in target_companies}
    for row in pick_rows:
        company = _row_company(row)
        if company in target_companies and _is_in_date_window(row, view_period_start, view_period_end):
            pick_rows_by_company.setdefault(company, []).append(row)
    for row in dispatch_rows:
        company = _row_company(row)
        if company in target_companies and _is_in_date_window(row, view_period_start, view_period_end):
            dispatch_rows_by_company.setdefault(company, []).append(row)

    def _metric_rows_for_company(metric: dict[str, str], company: str) -> list[dict[str, Any]]:
        row_id = str(metric["id"])
        prefix = str(metric.get("prefix") or "")
        company_pick_rows = pick_rows_by_company.get(company, [])
        if row_id.endswith("_picked_orders"):
            by_order: dict[str, dict[str, Any]] = {}
            for row in company_pick_rows:
                order = _row_order_number(row)
                if order.startswith(prefix) and _row_picked_qty(row) >= 1 and order not in by_order:
                    by_order[order] = row
            return list(by_order.values())
        if row_id.endswith("_picked_rows") or row_id.endswith("_picked_pcs"):
            return [
                row
                for row in company_pick_rows
                if _order_starts_with(row, prefix)
                and _row_pick_zone(row) != "H"
                and _row_picked_qty(row) >= 1
            ]
        if row_id in {"store_full_pallets", "ecom_pallet"}:
            return [
                row
                for row in company_pick_rows
                if _order_starts_with(row, prefix)
                and _row_pick_zone(row) == "H"
                and _row_picked_qty(row) >= 1
            ]
        if row_id == "store_loaded_pallets":
            return [
                row
                for row in dispatch_rows_by_company.get(company, [])
                if not _row_parent_pick_pall(row)
            ]
        return []

    def _package_count_for_pick_row(row: dict[str, Any]) -> float:
        item = _row_text(row, "item_num", "Artikel", "Artikelnr", "article", "item").strip()
        raw_company = _row_text(row, "company", "Company", "Bolag", "bolag").strip()
        company = _row_company(row)
        ladder = (
            package_ladders.get((item, raw_company))
            or package_ladders.get((item, company))
            or package_ladders.get((item.upper(), company))
            or package_ladders.get((item, ""))
            or package_ladders.get((item.upper(), ""))
            or default_package_ladder
        )
        packages = split_quantity_into_packages(_row_picked_qty(row), ladder)
        return float(sum(packages.values()))

    def _metric_trace_amounts(row_id: str, rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], float]]:
        if row_id.endswith("_picked_pcs"):
            return [(row, amount) for row in rows if (amount := _package_count_for_pick_row(row)) > 0]
        return [(row, 1.0) for row in rows]

    for company in sorted(target_companies):
        if not company:
            continue
        for metric in OUTBOUND_METRICS:
            row_id = str(metric["id"])
            rows = _metric_rows_for_company(metric, company)
            trace_amounts = _metric_trace_amounts(row_id, rows)
            count = float(sum(amount for _row, amount in trace_amounts)) if row_id.endswith("_picked_pcs") else float(len(rows))
            price = float((prices.get(row_id) or {}).get(company) or 0.0)
            revenue = count * price
            branch_key = str(metric["branch"])
            branch_summary_key = f"outbound_{branch_key}_income"

            metric_rows.append(
                {
                    "company": company,
                    "branch": branch_key,
                    "branch_label": metric["branch_label"],
                    "metric_id": row_id,
                    "label": metric["label"],
                    "unit": metric["unit"],
                    "count": _round_qty(count),
                    "price": _round_money(price),
                    "revenue": _round_money(revenue),
                }
            )
            summary["outbound_income"] += revenue
            summary[branch_summary_key] = summary.get(branch_summary_key, 0.0) + revenue
            if row_id.endswith("_picked_orders"):
                summary["outbound_picked_orders"] += count
            elif row_id.endswith("_picked_rows"):
                summary["outbound_picked_rows"] += count
            elif row_id.endswith("_picked_pcs"):
                summary["outbound_picked_pcs"] += count
            elif row_id in {"store_full_pallets", "ecom_pallet"}:
                summary["outbound_full_pallets"] += count
            elif row_id == "store_loaded_pallets":
                summary["outbound_loaded_pallets"] += count

            company_summary = company_summaries.setdefault(
                company,
                {
                    "company": company,
                    "outbound_income": 0.0,
                    "outbound_store_income": 0.0,
                    "outbound_ecom_income": 0.0,
                    "outbound_picked_orders": 0.0,
                    "outbound_picked_rows": 0.0,
                    "outbound_picked_pcs": 0.0,
                    "outbound_full_pallets": 0.0,
                    "outbound_loaded_pallets": 0.0,
                },
            )
            company_summary["outbound_income"] += revenue
            company_summary[branch_summary_key] = company_summary.get(branch_summary_key, 0.0) + revenue
            if row_id.endswith("_picked_orders"):
                company_summary["outbound_picked_orders"] += count
            elif row_id.endswith("_picked_rows"):
                company_summary["outbound_picked_rows"] += count
            elif row_id.endswith("_picked_pcs"):
                company_summary["outbound_picked_pcs"] += count
            elif row_id in {"store_full_pallets", "ecom_pallet"}:
                company_summary["outbound_full_pallets"] += count
            elif row_id == "store_loaded_pallets":
                company_summary["outbound_loaded_pallets"] += count

            if count <= 0 and revenue <= 0:
                continue
            start_node = _add_node(nodes, company, "outbound:start", "Outbound", "outbound_source", 0)
            branch_node = _add_node(nodes, company, f"outbound:{branch_key}", str(metric["branch_label"]), "outbound_branch", 1)
            metric_node = _add_node(nodes, company, f"outbound:{row_id}", str(metric["label"]), "outbound_metric", 2)
            for node in (start_node, branch_node, metric_node):
                node["value"] += revenue
                node["revenue"] += revenue
                node["outbound_revenue"] += revenue
                node["labels"] += count
                node["unit_label"] = "st"
            start_link_key = f'{start_node["id"]}->{branch_node["id"]}'
            metric_link_key = f'{branch_node["id"]}->{metric_node["id"]}'
            _add_link(links, start_node["id"], branch_node["id"], company, revenue, count, outbound_revenue=revenue)
            _add_link(links, branch_node["id"], metric_node["id"], company, revenue, count, outbound_revenue=revenue)
            for row, amount in trace_amounts:
                node_ids = [start_node["id"], branch_node["id"], metric_node["id"]]
                link_keys = [start_link_key, metric_link_key]
                if include_trace_details:
                    trace_rows.append(
                        _outbound_trace_row(
                            row,
                            metric=metric,
                            company=company,
                            amount=amount,
                            revenue=amount * price,
                            node_ids=node_ids,
                            link_keys=link_keys,
                        )
                    )
                else:
                    stamp = _row_datetime(row)
                    trace_rows.append(
                        _minimal_trace_row(
                            company=company,
                            received_date=stamp.date().isoformat() if stamp else "",
                            consumed=True,
                            node_ids=node_ids,
                            link_keys=link_keys,
                            trace_type="outbound",
                        )
                    )

    node_rows: list[dict] = []
    for node in nodes.values():
        node["value"] = _round_money(node["value"])
        node["revenue"] = _round_money(node["revenue"])
        node["outbound_revenue"] = _round_money(node["outbound_revenue"])
        node["labels"] = _round_qty(node["labels"])
        node_rows.append(node)
    node_rows.sort(key=lambda item: (item["company"], item["stage"], item["label"]))

    link_rows: list[dict] = []
    for link in links.values():
        link["value"] = _round_money(link["value"])
        link["revenue"] = _round_money(link["revenue"])
        link["outbound_revenue"] = _round_money(link["outbound_revenue"])
        link["labels"] = _round_qty(link["labels"])
        if link["outbound_revenue"] > 0:
            link["unit_label"] = "st"
        link_rows.append(link)
    link_rows.sort(key=lambda item: (item["company"], item["source"], item["target"]))

    for key in list(summary):
        summary[key] = _round_money(summary[key]) if "income" in key or "revenue" in key else _round_qty(summary[key])
    for row in company_summaries.values():
        for key in list(row):
            if key == "company":
                continue
            row[key] = _round_money(row[key]) if "income" in key or "revenue" in key else _round_qty(row[key])

    return {
        "nodes": node_rows,
        "links": link_rows,
        "trace_rows": trace_rows,
        "metrics": sorted(metric_rows, key=lambda item: (item["company"], item["branch"], item["label"])),
        "summary": summary,
        "companies": sorted(company_summaries.values(), key=lambda item: item["company"]),
    }


def _sync_branch_revenue(branch: TraceBranch) -> None:
    branch.revenue = max(0.0, float(branch.label_revenue or 0.0) + float(branch.purchase_line_revenue or 0.0))


def _normalize_process_point_key(value: Any) -> str:
    key = normalize_process(value).replace(" ", "_")
    return PROCESS_POINT_ALIASES.get(key, key)


def _process_points_from_kpi(rows: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    points: dict[tuple[str, str], float] = {}
    targets = parse_kpi_targets([dict(row) for row in rows or []])
    rules = parse_kpi_rule_rows([dict(row) for row in SQL_REFERENCE_KPI_RULE_ROWS])
    rule_metrics: dict[str, set[str]] = {}
    for rule in rules:
        rule_metrics.setdefault(_normalize_process_point_key(rule.process_key), set()).add(rule.metric)

    for (company, raw_process), target in targets.items():
        process = _normalize_process_point_key(raw_process)
        metric = PROCESS_DEFAULT_METRIC.get(process)
        if metric not in (target.points or {}) or float((target.points or {}).get(metric) or 0.0) <= 0:
            candidates = rule_metrics.get(process, set())
            if candidates:
                metric = next(
                    (
                        candidate
                        for candidate in ("rows", "packages", "pallets", "orders")
                        if candidate in candidates and float((target.points or {}).get(candidate) or 0.0) > 0
                    ),
                    metric,
                )
        value = float((target.points or {}).get(metric or "") or 0.0)
        if value > 0:
            points[(company, process)] = value
            points.setdefault(("", process), value)
    return points


def _process_point_value(point_map: dict[tuple[str, str], float], company: str, process_key: str) -> float:
    key = _normalize_process_point_key(process_key)
    company_key = clean_productivity_finance_company_code(company)
    return float(point_map.get((company_key, key)) or point_map.get(("", key)) or 0.0)


def _append_process(
    branch: TraceBranch,
    process_key: str,
    point_map: dict[tuple[str, str], float],
    warnings: list[dict],
    *,
    source: str,
) -> None:
    key = _normalize_process_point_key(process_key)
    if not key:
        return
    if branch.processes and branch.processes[-1].key == key:
        return
    points = _process_point_value(point_map, branch.company, key)
    if points <= 0:
        warnings.append(
            {
                "code": "missing_process_points",
                "process_key": key,
                "process_label": PROCESS_LABELS.get(key, key),
                "message": f"Saknar KPI-poäng för {PROCESS_LABELS.get(key, key)}.",
            }
        )
    label = PROCESS_LABELS.get(key, key)
    branch.processes.append(ProcessVisit(key=key, label=label, points=points, source=source))
    branch.trace_steps.append(label)


def _classify_trans(row: dict[str, Any]) -> tuple[str | None, str]:
    trans_type = _normalize_type(_row_value(row, "type", "Typ"))
    loc_to = _row_text(row, "loc_to", "Till").upper()
    if trans_type == "26" and loc_to.startswith("AS"):
        return "DECANTING", "open_autostore"
    if trans_type == "111" and loc_to.startswith("HBW"):
        return "HBW", "open_hbw"
    if trans_type == "22":
        return "MANUAL_BUFFER", "open_buffer"
    if trans_type in {"21", "27", "29"}:
        return "PUTAWAY_PICK", "open_pick_location"
    return None, ""


def _pick_location_key(company: str, warehouse: str, item: str, location: str) -> tuple[str, str, str, str]:
    return (company.upper(), warehouse.upper(), item.upper(), location.upper())


def _consume_pick_queue(
    queues: dict[tuple[str, str, str, str], list[PickQueueEntry]],
    branches: dict[str, TraceBranch],
    key: tuple[str, str, str, str],
    qty: float,
    *,
    mark_consumed: bool,
) -> list[tuple[TraceBranch, float]]:
    consumed: list[tuple[TraceBranch, float]] = []
    remaining = max(0.0, float(qty or 0.0))
    queue = queues.setdefault(key, [])
    while remaining > 0 and queue:
        entry = queue[0]
        take = min(entry.qty, remaining)
        entry.qty -= take
        remaining -= take
        if entry.branch_id and entry.branch_id in branches:
            branch = branches[entry.branch_id]
            consumed.append((branch, take))
            if mark_consumed:
                branch.qty = max(0.0, branch.qty - take)
                if branch.qty <= 0.0001:
                    branch.qty = 0.0
                    branch.consumed = True
                    branch.status = "consumed"
        if entry.qty <= 0.0001:
            queue.pop(0)
    return consumed


def _branch_matches_pall(branch: TraceBranch, pall: str) -> bool:
    if not branch.active or branch.revenue <= 0:
        return False
    return bool(_pall_aliases(branch.current_pall) & _pall_aliases(pall))


def _event_sort_key(row: dict[str, Any]) -> tuple[datetime, str]:
    stamp = _row_datetime(row) or datetime.min
    return stamp, _row_id(row, 0)


def _build_current_pallet_locations(rows: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for row in rows or []:
        company = _row_company(row)
        pall = _row_pall(row)
        location = _row_text(row, "location", "Lagerplats", "loc", "Lokation").upper()
        if company and pall and location:
            result[(company, _normalize_pall(pall))] = location
    return result


def _status_from_current_location(branch: TraceBranch, current_locations: dict[tuple[str, str], str]) -> str:
    if branch.consumed:
        return "consumed"
    if branch.status == "open_pick_location":
        return branch.status
    location = current_locations.get((branch.company, _normalize_pall(branch.current_pall)), "").upper()
    probe = location or branch.location.upper() or branch.current_pall.upper()
    if probe.startswith("AS"):
        return "open_autostore"
    if probe.startswith("HBW"):
        return "open_hbw"
    if branch.status in {"open_autostore", "open_hbw", "open_buffer"}:
        return branch.status
    if location:
        return "open_buffer"
    return branch.status or "open_not_putaway"


def _node_id(company: str, key: str) -> str:
    return f"{company}:{key}"


def _add_node(nodes: dict[str, dict], company: str, key: str, label: str, node_type: str, stage: int) -> dict:
    node_id = _node_id(company, key)
    node = nodes.setdefault(
        node_id,
        {
            "id": node_id,
            "company": company,
            "key": key,
            "label": label,
            "type": node_type,
            "stage": stage,
            "value": 0.0,
            "revenue": 0.0,
            "label_revenue": 0.0,
            "purchase_line_revenue": 0.0,
            "outbound_revenue": 0.0,
            "labels": 0.0,
            "points": 0.0,
            "confidence": "high",
        },
    )
    return node


def _add_link(
    links: dict[tuple[str, str, str], dict],
    source: str,
    target: str,
    company: str,
    revenue: float,
    labels: float,
    *,
    label_revenue: float = 0.0,
    purchase_line_revenue: float = 0.0,
    outbound_revenue: float = 0.0,
) -> None:
    if revenue <= 0 and labels <= 0:
        return
    key = (source, target, company)
    link = links.setdefault(
        key,
        {
            "source": source,
            "target": target,
            "company": company,
            "value": 0.0,
            "revenue": 0.0,
            "label_revenue": 0.0,
            "purchase_line_revenue": 0.0,
            "outbound_revenue": 0.0,
            "labels": 0.0,
            "confidence": "high",
        },
    )
    link["value"] += revenue
    link["revenue"] += revenue
    link["label_revenue"] += label_revenue
    link["purchase_line_revenue"] += purchase_line_revenue
    link["outbound_revenue"] += outbound_revenue
    link["labels"] += labels


def _trace_path_steps(branch: TraceBranch, terminal_label: str) -> list[str]:
    steps = [f"Mottagning {branch.origin_pall or branch.current_pall}".strip()]
    steps.extend(branch.trace_steps or [visit.label for visit in branch.processes])
    steps.append(terminal_label)
    deduped: list[str] = []
    for step in steps:
        text = _clean_text(step)
        if text and (not deduped or deduped[-1] != text):
            deduped.append(text)
    return deduped


def _trace_row_for_branch(
    branch: TraceBranch,
    *,
    terminal_key: str,
    terminal_label: str,
    current_locations: dict[tuple[str, str], str],
    node_ids: list[str],
    link_keys: list[str],
) -> dict[str, Any]:
    current_location = current_locations.get((branch.company, _normalize_pall(branch.current_pall)), "") or branch.location
    path_steps = _trace_path_steps(branch, terminal_label)
    row: dict[str, Any] = {
        "branch_id": branch.id,
        "origin_id": branch.origin_id,
        "company": branch.company,
        "warehouse": branch.warehouse,
        "item": branch.item,
        "origin_pall": branch.origin_pall or branch.current_pall,
        "current_pall": branch.current_pall,
        "current_location": current_location,
        "purchase_number": branch.purchase_number,
        "purchase_line": branch.purchase_line,
        "received_date": branch.received_date.isoformat() if branch.received_date else "",
        "source_row_id": branch.source_row_id,
        "qty_remaining": _round_qty(branch.qty),
        "revenue": _round_money(branch.revenue),
        "label_revenue": _round_money(branch.label_revenue),
        "purchase_line_revenue": _round_money(branch.purchase_line_revenue),
        "label_fraction": _round_qty(branch.label_fraction),
        "status": terminal_key,
        "status_label": terminal_label,
        "consumed": bool(branch.consumed),
        "confidence": branch.confidence,
        "path": " -> ".join(path_steps),
        "node_ids": list(node_ids),
        "link_keys": list(link_keys),
    }
    for index, step in enumerate(path_steps, start=1):
        row[f"step_{index}"] = step
    return row


def _minimal_trace_row(
    *,
    company: str,
    received_date: date | str | None,
    consumed: bool,
    node_ids: list[str],
    link_keys: list[str],
    trace_type: str = "inbound",
) -> dict[str, Any]:
    if isinstance(received_date, date):
        received = received_date.isoformat()
    else:
        received = str(received_date or "")
    return {
        "trace_type": trace_type,
        "company": company,
        "received_date": received,
        "consumed": bool(consumed),
        "node_ids": list(node_ids),
        "link_keys": list(link_keys),
    }


def _finalize_sankey(
    branches: list[TraceBranch],
    *,
    only_consumed: bool,
    warnings: list[dict],
    current_locations: dict[tuple[str, str], str],
    branch_predicate: Callable[[TraceBranch], bool] | None = None,
    include_trace_details: bool = True,
) -> tuple[list[dict], list[dict], list[dict], dict, list[dict]]:
    nodes: dict[str, dict] = {}
    links: dict[tuple[str, str, str], dict] = {}
    process_rows: dict[tuple[str, str], dict] = {}
    trace_rows: list[dict] = []
    summary = {
        "gross_income": 0.0,
        "gross_income_labels": 0.0,
        "gross_income_purchase_lines": 0.0,
        "labels_traced": 0.0,
        "labels_consumed": 0.0,
        "labels_open": 0.0,
        "unallocated_revenue": 0.0,
    }
    warned_missing_points: set[str] = set()

    for branch in branches:
        if not branch.active or branch.revenue <= 0:
            continue
        if branch_predicate is not None and not branch_predicate(branch):
            continue
        if only_consumed and not branch.consumed:
            continue
        company = branch.company or "OKANT"
        status_key = _status_from_current_location(branch, current_locations)
        terminal_key = status_key
        terminal_label = OPEN_STATUS_LABELS.get(status_key, OPEN_STATUS_LABELS["open_not_putaway"])
        summary["gross_income"] += branch.revenue
        summary["gross_income_labels"] += branch.label_revenue
        summary["gross_income_purchase_lines"] += branch.purchase_line_revenue
        summary["labels_traced"] += branch.label_fraction
        if branch.consumed:
            summary["labels_consumed"] += branch.label_fraction
        else:
            summary["labels_open"] += branch.label_fraction

        start_node = _add_node(nodes, company, "start", "Mottaget inbound", "source", 0)
        start_node["value"] += branch.revenue
        start_node["revenue"] += branch.revenue
        start_node["label_revenue"] += branch.label_revenue
        start_node["purchase_line_revenue"] += branch.purchase_line_revenue
        start_node["labels"] += branch.label_fraction

        previous_node_id = start_node["id"]
        path_node_ids = [previous_node_id]
        path_link_keys: list[str] = []
        total_points = sum(max(0.0, visit.points) for visit in branch.processes)
        if total_points <= 0 and branch.processes:
            summary["unallocated_revenue"] += branch.revenue
            for visit in branch.processes:
                if visit.key not in warned_missing_points:
                    warned_missing_points.add(visit.key)
                    warnings.append(
                        {
                            "code": "unallocated_process_revenue",
                            "process_key": visit.key,
                            "message": f"Intäkt kunde inte fördelas för {visit.label} eftersom poäng saknas.",
                        }
                    )

        for index, visit in enumerate(branch.processes, start=1):
            node = _add_node(nodes, company, f"process:{visit.key}", visit.label, "process", index)
            share = (visit.points / total_points) if total_points > 0 and visit.points > 0 else 0.0
            allocated_label_revenue = branch.label_revenue * share
            allocated_purchase_line_revenue = branch.purchase_line_revenue * share
            allocated = allocated_label_revenue + allocated_purchase_line_revenue
            node["value"] += branch.revenue
            node["revenue"] += allocated
            node["label_revenue"] += allocated_label_revenue
            node["purchase_line_revenue"] += allocated_purchase_line_revenue
            node["labels"] += branch.label_fraction
            node["points"] += visit.points
            process_key = (company, visit.key)
            process = process_rows.setdefault(
                process_key,
                {
                    "company": company,
                    "process_key": visit.key,
                    "label": visit.label,
                    "points": 0.0,
                    "revenue": 0.0,
                    "label_revenue": 0.0,
                    "purchase_line_revenue": 0.0,
                    "labels": 0.0,
                    "share": 0.0,
                },
            )
            process["points"] += visit.points
            process["revenue"] += allocated
            process["label_revenue"] += allocated_label_revenue
            process["purchase_line_revenue"] += allocated_purchase_line_revenue
            process["labels"] += branch.label_fraction
            link_key = f'{previous_node_id}->{node["id"]}'
            _add_link(
                links,
                previous_node_id,
                node["id"],
                company,
                branch.revenue,
                branch.label_fraction,
                label_revenue=branch.label_revenue,
                purchase_line_revenue=branch.purchase_line_revenue,
            )
            path_link_keys.append(link_key)
            previous_node_id = node["id"]
            path_node_ids.append(previous_node_id)

        terminal = _add_node(nodes, company, f"terminal:{terminal_key}", terminal_label, "terminal", 99)
        terminal["value"] += branch.revenue
        terminal["label_revenue"] += branch.label_revenue
        terminal["purchase_line_revenue"] += branch.purchase_line_revenue
        terminal["labels"] += branch.label_fraction
        if branch.confidence != "high":
            terminal["confidence"] = branch.confidence
        terminal_link_key = f'{previous_node_id}->{terminal["id"]}'
        _add_link(
            links,
            previous_node_id,
            terminal["id"],
            company,
            branch.revenue,
            branch.label_fraction,
            label_revenue=branch.label_revenue,
            purchase_line_revenue=branch.purchase_line_revenue,
        )
        path_link_keys.append(terminal_link_key)
        path_node_ids.append(terminal["id"])
        if include_trace_details:
            trace_rows.append(
                _trace_row_for_branch(
                    branch,
                    terminal_key=terminal_key,
                    terminal_label=terminal_label,
                    current_locations=current_locations,
                    node_ids=path_node_ids,
                    link_keys=path_link_keys,
                )
            )
        else:
            trace_rows.append(
                _minimal_trace_row(
                    company=company,
                    received_date=branch.received_date,
                    consumed=branch.consumed,
                    node_ids=path_node_ids,
                    link_keys=path_link_keys,
                )
            )

    gross = summary["gross_income"]
    for process in process_rows.values():
        process["revenue"] = _round_money(process["revenue"])
        process["label_revenue"] = _round_money(process["label_revenue"])
        process["purchase_line_revenue"] = _round_money(process["purchase_line_revenue"])
        process["points"] = _round_qty(process["points"])
        process["labels"] = _round_qty(process["labels"])
        process["share"] = round((process["revenue"] / gross) if gross > 0 else 0.0, 4)

    node_rows = []
    for node in nodes.values():
        node["value"] = _round_money(node["value"])
        node["revenue"] = _round_money(node["revenue"])
        node["label_revenue"] = _round_money(node["label_revenue"])
        node["purchase_line_revenue"] = _round_money(node["purchase_line_revenue"])
        node["outbound_revenue"] = _round_money(node["outbound_revenue"])
        node["labels"] = _round_qty(node["labels"])
        node["points"] = _round_qty(node["points"])
        node_rows.append(node)
    node_rows.sort(key=lambda item: (item["company"], item["stage"], item["label"]))

    link_rows = []
    for link in links.values():
        link["value"] = _round_money(link["value"])
        link["revenue"] = _round_money(link["revenue"])
        link["label_revenue"] = _round_money(link["label_revenue"])
        link["purchase_line_revenue"] = _round_money(link["purchase_line_revenue"])
        link["outbound_revenue"] = _round_money(link["outbound_revenue"])
        link["labels"] = _round_qty(link["labels"])
        link_rows.append(link)
    link_rows.sort(key=lambda item: (item["company"], item["source"], item["target"]))

    for key in list(summary):
        summary[key] = _round_money(summary[key]) if "revenue" in key or "income" in key else _round_qty(summary[key])
    return node_rows, link_rows, sorted(process_rows.values(), key=lambda item: (item["company"], item["label"])), summary, trace_rows


def build_sankey_inbound_payload(
    *,
    source_rows: dict[str, list[dict[str, Any]]],
    finance_settings: dict,
    company_codes: list[str],
    period_start: date,
    period_end: date,
    follow_until: date,
    period_type: str = "cohort",
    period_label: str | None = None,
    company_filter: str | None = None,
    only_consumed: bool = False,
    process_points: dict[str, float] | None = None,
    source_status: list[dict] | None = None,
    warnings: list[dict] | None = None,
) -> dict:
    normalized_company_filter = clean_productivity_finance_company_code(company_filter)
    allowed_companies = {clean_productivity_finance_company_code(code) for code in company_codes if clean_productivity_finance_company_code(code)}
    if normalized_company_filter and normalized_company_filter != "ALL":
        allowed_companies = {normalized_company_filter}
    receive_rows = source_rows.get("receive") or []
    trans_rows = source_rows.get("trans") or []
    pick_rows = source_rows.get("pick") or []
    dispatch_rows = source_rows.get("dispatch") or []
    buffer_rows = source_rows.get("buffer") or []
    kpi_rows = source_rows.get("kpi") or []
    alias_rows = source_rows.get("item_alias") or []
    warnings_out = list(warnings or [])

    row_companies = sorted({_row_company(row) for row in receive_rows + trans_rows + pick_rows + dispatch_rows if _row_company(row)})
    if not allowed_companies:
        allowed_companies = set(row_companies)
    all_company_codes = sorted(allowed_companies or set(row_companies))
    label_prices, purchase_line_prices, price_warnings = _inbound_prices(finance_settings, all_company_codes)
    outbound_prices, outbound_price_warnings = _outbound_prices(finance_settings, all_company_codes)
    warnings_out.extend(price_warnings)
    warnings_out.extend(outbound_price_warnings)

    point_map = {
        ("", _normalize_process_point_key(key)): float(value or 0.0)
        for key, value in (process_points or {}).items()
    }
    if not point_map:
        point_map = _process_points_from_kpi(kpi_rows)

    zeroing_by_pall: dict[tuple[str, str], list[datetime]] = {}
    for row in receive_rows:
        if _normalize_type(_row_value(row, "type", "Typ")) != ZEROING_RECEIVE_TYPE:
            continue
        company = _row_company(row)
        pall = _normalize_pall(_row_pall(row))
        stamp = _row_datetime(row)
        if company and pall and stamp:
            zeroing_by_pall.setdefault((company, pall), []).append(stamp)

    branches: list[TraceBranch] = []
    branch_map: dict[str, TraceBranch] = {}
    # Index (bolag, pall-alias) -> positioner i branches, så vi slipper skanna hela
    # branches-listan per trans/pick-event (tidigare O(events × grenar)). Vi indexerar
    # under alla pall-alias och lägger till nya alias när current_pall ändras; läsning
    # dedupar via set och filtrerar med _branch_matches_pall, så resultatet blir
    # identiskt med den tidigare linjära skanningen men i global gren-ordning.
    pall_index: dict[tuple[str, str], list[int]] = {}
    branch_index: dict[str, int] = {}

    def _register_pall(idx: int, branch: TraceBranch) -> None:
        for alias in _pall_aliases(branch.current_pall):
            pall_index.setdefault((branch.company, alias), []).append(idx)

    def _index_branch(branch: TraceBranch) -> None:
        idx = len(branches)
        branches.append(branch)
        branch_map[branch.id] = branch
        branch_index[branch.id] = idx
        _register_pall(idx, branch)

    def _matching_branches(company: str, pall: str) -> list[TraceBranch]:
        candidate_indices: set[int] = set()
        for alias in _pall_aliases(pall):
            candidate_indices.update(pall_index.get((company, alias), ()))
        result: list[TraceBranch] = []
        for idx in sorted(candidate_indices):
            branch = branches[idx]
            if branch.company == company and _branch_matches_pall(branch, pall):
                result.append(branch)
        return result

    excluded_zeroed = 0
    filtered_receives: list[dict[str, Any]] = []
    purchase_line_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    missing_purchase_line_rows = 0
    for index, row in enumerate(receive_rows):
        company = _row_company(row)
        if not _company_allowed(company, allowed_companies):
            continue
        if not _is_in_date_window(row, period_start, period_end):
            continue
        receive_type = _normalize_type(_row_value(row, "type", "Typ"))
        if receive_type in EXCLUDED_RECEIVE_TYPES:
            continue
        qty = _row_number(row, "qty_suf", "Mottaget", "received_qty")
        if qty <= 0:
            continue
        pall = _normalize_pall(_row_pall(row))
        stamp = _row_datetime(row)
        zeroings = zeroing_by_pall.get((company, pall), [])
        if stamp and any(zero_stamp >= stamp for zero_stamp in zeroings):
            excluded_zeroed += 1
            continue
        origin_id = _row_id(row, index)
        entry = {
            "index": index,
            "row": row,
            "company": company,
            "warehouse": _row_warehouse(row),
            "item": _row_item(row),
            "pall": pall,
            "qty": qty,
            "origin_id": origin_id,
            "received_date": stamp.date() if stamp else None,
        }
        filtered_receives.append(entry)
        purchase_line_key = _purchase_line_key(row)
        if purchase_line_key:
            purchase_line_groups.setdefault(purchase_line_key, []).append(entry)
        else:
            missing_purchase_line_rows += 1

    purchase_line_revenue_by_origin: dict[str, float] = {}
    for key, entries in purchase_line_groups.items():
        if not entries:
            continue
        purchase_line_revenue = float(purchase_line_prices.get(key[0], 0.0))
        if purchase_line_revenue <= 0:
            continue
        share = purchase_line_revenue / len(entries)
        for entry in entries:
            origin_id = str(entry["origin_id"])
            purchase_line_revenue_by_origin[origin_id] = purchase_line_revenue_by_origin.get(origin_id, 0.0) + share

    if missing_purchase_line_rows and any(float(value or 0.0) > 0 for value in purchase_line_prices.values()):
        warnings_out.append(
            {
                "code": "missing_inbound_purchase_line_key",
                "count": missing_purchase_line_rows,
                "message": f"{missing_purchase_line_rows} mottagningar saknar inköpsnr eller rad och fick ingen inköpsradsintäkt.",
            }
        )

    for entry in filtered_receives:
        row = entry["row"]
        company = str(entry["company"])
        origin_id = str(entry["origin_id"])
        label_revenue = float(label_prices.get(company, 0.0))
        purchase_line_revenue = float(purchase_line_revenue_by_origin.get(origin_id, 0.0))
        branch = TraceBranch(
            id=f"{origin_id}:0",
            origin_id=origin_id,
            company=company,
            warehouse=str(entry["warehouse"]),
            item=str(entry["item"]),
            current_pall=str(entry["pall"]),
            qty=float(entry["qty"]),
            revenue=label_revenue + purchase_line_revenue,
            label_fraction=1.0,
            label_revenue=label_revenue,
            purchase_line_revenue=purchase_line_revenue,
            origin_pall=str(entry["pall"]),
            source_row_id=_row_text(row, "rowid", "Rowid", "Radid", "radid", "id") or origin_id,
            purchase_number=_row_purchase_number(row),
            purchase_line=_row_purchase_line(row),
            received_date=entry["received_date"],
        )
        _append_process(branch, "RECEIVING", point_map, warnings_out, source="receive")
        _index_branch(branch)

    if excluded_zeroed:
        warnings_out.append(
            {
                "code": "type_100_zeroed_receipts",
                "count": excluded_zeroed,
                "message": f"{excluded_zeroed} mottagningar exkluderades av typ 100-nollstallning.",
            }
        )

    decant_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in trans_rows:
        process_key, _status_key = _classify_trans(row)
        if process_key != "DECANTING":
            continue
        company = _row_company(row)
        if not _company_allowed(company, allowed_companies):
            continue
        pall = _normalize_pall(_row_pall(row))
        if company and pall:
            decant_groups.setdefault((company, pall), []).append(row)
    for rows in decant_groups.values():
        rows.sort(key=_event_sort_key)

    processed_decant_branches: set[tuple[str, str]] = set()
    pick_queues: dict[tuple[str, str, str, str], list[PickQueueEntry]] = {}

    events = []
    events.extend(("trans", row) for row in trans_rows if _company_allowed(_row_company(row), allowed_companies))
    events.extend(("receive", row) for row in receive_rows if _company_allowed(_row_company(row), allowed_companies))
    events.extend(("pick", row) for row in pick_rows if _company_allowed(_row_company(row), allowed_companies))
    events.sort(key=lambda item: _event_sort_key(item[1]))

    for source_key, row in events:
        if source_key == "trans":
            pall = _normalize_pall(_row_pall(row))
            company = _row_company(row)
            process_key, status_key = _classify_trans(row)
            if not process_key or not pall:
                continue
            matching = _matching_branches(company, pall)
            if process_key == "DECANTING":
                for branch in list(matching):
                    split_key = (branch.id, pall)
                    if split_key in processed_decant_branches:
                        continue
                    processed_decant_branches.add(split_key)
                    group = decant_groups.get((company, pall), [row])
                    total_child_qty = sum(max(0.0, _row_number(item, "qty", "Antal", "qty_suf")) for item in group)
                    has_remaining = branch.qty > total_child_qty + 0.0001
                    child_count = len(group) + (1 if has_remaining else 0)
                    if child_count <= 0:
                        continue
                    share_label_revenue = branch.label_revenue / child_count
                    share_purchase_line_revenue = branch.purchase_line_revenue / child_count
                    share_revenue = share_label_revenue + share_purchase_line_revenue
                    share_label = branch.label_fraction / child_count
                    original_revenue = branch.revenue
                    original_label = branch.label_fraction
                    if has_remaining:
                        branch.label_revenue = share_label_revenue
                        branch.purchase_line_revenue = share_purchase_line_revenue
                        _sync_branch_revenue(branch)
                        branch.label_fraction = share_label
                        branch.qty = max(0.0, branch.qty - total_child_qty)
                    else:
                        branch.active = False
                        branch.revenue = 0.0
                        branch.label_revenue = 0.0
                        branch.purchase_line_revenue = 0.0
                        branch.label_fraction = 0.0
                        branch.qty = 0.0
                    for child_index, item in enumerate(group, start=1):
                        child_pall = _normalize_pall(_row_text(item, "loc_to", "Till") or _row_pall(item))
                        child_qty = max(0.0, _row_number(item, "qty", "Antal", "qty_suf"))
                        child = TraceBranch(
                            id=f"{branch.id}:AS{child_index}",
                            origin_id=branch.origin_id,
                            company=branch.company,
                            warehouse=branch.warehouse,
                            item=branch.item,
                            current_pall=child_pall,
                            qty=child_qty,
                            revenue=share_revenue,
                            label_fraction=share_label,
                            label_revenue=share_label_revenue,
                            purchase_line_revenue=share_purchase_line_revenue,
                            origin_pall=branch.origin_pall,
                            source_row_id=branch.source_row_id,
                            purchase_number=branch.purchase_number,
                            purchase_line=branch.purchase_line,
                            received_date=branch.received_date,
                            trace_steps=list(branch.trace_steps),
                            processes=list(branch.processes),
                            status="open_autostore",
                        )
                        _append_process(child, "DECANTING", point_map, warnings_out, source="trans")
                        _index_branch(child)
                    if child_count > 1 and original_revenue > 0:
                        warnings_out.append(
                            {
                                "code": "equal_split_applied",
                                "origin_id": branch.origin_id,
                                "branches": child_count,
                                "message": "Inboundintäkt delades lika mellan split-grenar.",
                            }
                        )
                        if original_label <= 0:
                            branch.label_fraction = 0.0
                continue
            for branch in matching:
                _append_process(branch, process_key, point_map, warnings_out, source="trans")
                branch.status = status_key or branch.status
                loc_to = _row_text(row, "loc_to", "Till").upper()
                if loc_to:
                    branch.location = loc_to
                if status_key == "open_pick_location":
                    key = _pick_location_key(branch.company, branch.warehouse, branch.item, loc_to)
                    queue = pick_queues.setdefault(key, [])
                    prior_qty = max(0.0, _row_number(row, "qty_pre", "Saldo före", "Saldo fore", "saldo_pre"))
                    if prior_qty > 0 and not queue:
                        queue.append(PickQueueEntry(None, prior_qty))
                        branch.confidence = "partial_fifo"
                    queue.append(PickQueueEntry(branch.id, branch.qty))
                elif loc_to and loc_to.startswith("AS"):
                    new_current = _normalize_pall(loc_to)
                    if new_current != branch.current_pall:
                        branch.current_pall = new_current
                        _register_pall(branch_index[branch.id], branch)

        elif source_key == "receive":
            if _normalize_type(_row_value(row, "type", "Typ")) != BUFFER_UPDATE_RECEIVE_TYPE:
                continue
            company = _row_company(row)
            location = _row_text(row, "location", "Lokation", "loc_from", "Fran", "Från").upper()
            item = _row_item(row)
            warehouse = _row_warehouse(row)
            new_pall = _normalize_pall(_row_pall(row))
            qty = max(0.0, _row_number(row, "qty_suf", "Mottaget", "qty"))
            if location and item and qty > 0:
                key = _pick_location_key(company, warehouse, item, location)
                moved = _consume_pick_queue(pick_queues, branch_map, key, qty, mark_consumed=False)
                for move_index, (branch, moved_qty) in enumerate(moved, start=1):
                    if branch.revenue <= 0:
                        continue
                    if moved_qty >= branch.qty - 0.0001:
                        child_revenue = branch.revenue
                        child_label_revenue = branch.label_revenue
                        child_purchase_line_revenue = branch.purchase_line_revenue
                        child_label = branch.label_fraction
                        branch.active = False
                        branch.revenue = 0.0
                        branch.label_revenue = 0.0
                        branch.purchase_line_revenue = 0.0
                        branch.label_fraction = 0.0
                        branch.qty = 0.0
                    else:
                        child_revenue = branch.revenue / 2
                        child_label_revenue = branch.label_revenue / 2
                        child_purchase_line_revenue = branch.purchase_line_revenue / 2
                        child_label = branch.label_fraction / 2
                        branch.label_revenue -= child_label_revenue
                        branch.purchase_line_revenue -= child_purchase_line_revenue
                        _sync_branch_revenue(branch)
                        branch.label_fraction -= child_label
                        branch.qty = max(0.0, branch.qty - moved_qty)
                    child = TraceBranch(
                        id=f"{branch.id}:BU{move_index}",
                        origin_id=branch.origin_id,
                        company=branch.company,
                        warehouse=branch.warehouse,
                        item=branch.item,
                        current_pall=new_pall,
                        qty=moved_qty,
                        revenue=child_revenue,
                        label_fraction=child_label,
                        label_revenue=child_label_revenue,
                        purchase_line_revenue=child_purchase_line_revenue,
                        origin_pall=branch.origin_pall,
                        source_row_id=branch.source_row_id,
                        purchase_number=branch.purchase_number,
                        purchase_line=branch.purchase_line,
                        received_date=branch.received_date,
                        trace_steps=list(branch.trace_steps),
                        processes=list(branch.processes),
                        status="open_buffer",
                        confidence=branch.confidence,
                    )
                    _append_process(child, "BUFFER_UPDATE", point_map, warnings_out, source="receive")
                    _index_branch(child)
                if not moved and new_pall:
                    for branch in _matching_branches(company, new_pall):
                        _append_process(branch, "BUFFER_UPDATE", point_map, warnings_out, source="receive")
                        branch.status = "open_buffer"
            elif new_pall:
                for branch in _matching_branches(company, new_pall):
                    _append_process(branch, "BUFFER_UPDATE", point_map, warnings_out, source="receive")
                    branch.status = "open_buffer"

        elif source_key == "pick":
            company = _row_company(row)
            warehouse = _row_warehouse(row)
            item = _row_item(row)
            location = _row_text(row, "location", "Lokation", "pick_loc").upper()
            qty = max(0.0, _row_number(row, "qty_suf", "Plockat", "picked_qty", "qty"))
            if qty <= 0:
                continue
            pall = _normalize_pall(_row_pall(row))
            direct = _matching_branches(company, pall) if pall else []
            if direct:
                remaining = qty
                for branch in direct:
                    if remaining <= 0:
                        break
                    take = min(branch.qty, remaining) if branch.qty > 0 else remaining
                    branch.qty = max(0.0, branch.qty - take)
                    remaining -= take
                    if branch.qty <= 0.0001:
                        branch.qty = 0.0
                        branch.consumed = True
                        branch.status = "consumed"
                continue
            if location:
                key = _pick_location_key(company, warehouse, item, location)
                if key not in pick_queues:
                    warnings_out.append(
                        {
                            "code": "pick_location_owner_unknown",
                            "company": company,
                            "message": "Plockrad saknar känd inbound-agare i vald period.",
                        }
                    )
                _consume_pick_queue(pick_queues, branch_map, key, qty, mark_consumed=True)

    current_locations = _build_current_pallet_locations(buffer_rows)
    requested_period_type = str(period_type or "cohort").strip().lower()
    requested_period_label = period_label or _period_label(requested_period_type)

    def _view_period(period_name: str, start: date, end: date) -> dict[str, Any]:
        return {
            "type": period_name,
            "label": requested_period_label if period_name == requested_period_type else _period_label(period_name),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "follow_until": follow_until.isoformat(),
        }

    def _matches_view_company(company: str, view_company: str) -> bool:
        return view_company == "ALL" or company == view_company

    def _entry_matches_view(entry: dict[str, Any], view_company: str, view_start: date, view_end: date) -> bool:
        received_date = entry.get("received_date")
        return (
            isinstance(received_date, date)
            and view_start <= received_date <= view_end
            and _matches_view_company(str(entry.get("company") or ""), view_company)
        )

    def _build_view_payload(
        view_only_consumed: bool,
        view_warnings: list[dict],
        *,
        view_company_filter: str,
        view_period_type: str,
        view_period_start: date,
        view_period_end: date,
        trace_detail: bool = True,
    ) -> dict:
        def _branch_matches_view(branch: TraceBranch) -> bool:
            return (
                branch.received_date is not None
                and view_period_start <= branch.received_date <= view_period_end
                and _matches_view_company(branch.company, view_company_filter)
            )

        nodes, links, processes, traced_summary, trace_rows = _finalize_sankey(
            branches,
            only_consumed=view_only_consumed,
            warnings=view_warnings,
            current_locations=current_locations,
            branch_predicate=_branch_matches_view,
            include_trace_details=trace_detail,
        )
        outbound = _build_outbound_sankey(
            pick_rows=pick_rows,
            dispatch_rows=dispatch_rows,
            alias_rows=alias_rows,
            prices=outbound_prices,
            allowed_companies=all_company_codes,
            view_company_filter=view_company_filter,
            view_period_start=view_period_start,
            view_period_end=view_period_end,
            include_trace_details=trace_detail,
        )

        view_receive_entries = [
            entry
            for entry in filtered_receives
            if _entry_matches_view(entry, view_company_filter, view_period_start, view_period_end)
        ]
        view_purchase_keys = {
            key
            for key in (_purchase_line_key(entry["row"]) for entry in view_receive_entries)
            if key is not None
        }
        view_purchase_lines_by_company: dict[str, int] = {}
        for company, _purchase, _line in view_purchase_keys:
            view_purchase_lines_by_company[company] = view_purchase_lines_by_company.get(company, 0) + 1

        company_summaries: dict[str, dict] = {}
        for branch in branches:
            if not branch.active or branch.revenue <= 0:
                continue
            if not _branch_matches_view(branch):
                continue
            if view_only_consumed and not branch.consumed:
                continue
            company = branch.company or "OKANT"
            row = company_summaries.setdefault(
                company,
                {
                    "company": company,
                    "gross_income": 0.0,
                    "gross_income_labels": 0.0,
                    "gross_income_purchase_lines": 0.0,
                    "labels": 0.0,
                    "purchase_lines": 0.0,
                    "consumed_labels": 0.0,
                    "open_labels": 0.0,
                },
            )
            row["gross_income"] += branch.revenue
            row["gross_income_labels"] += branch.label_revenue
            row["gross_income_purchase_lines"] += branch.purchase_line_revenue
            row["labels"] += branch.label_fraction
            if branch.consumed:
                row["consumed_labels"] += branch.label_fraction
            else:
                row["open_labels"] += branch.label_fraction

        for company, count in view_purchase_lines_by_company.items():
            if company not in company_summaries:
                continue
            company_summaries[company]["purchase_lines"] = count

        summary = {
            "gross_income": _round_money(traced_summary["gross_income"] + outbound["summary"]["outbound_income"]),
            "inbound_income": _round_money(traced_summary["gross_income"]),
            "gross_income_labels": _round_money(traced_summary["gross_income_labels"]),
            "gross_income_purchase_lines": _round_money(traced_summary["gross_income_purchase_lines"]),
            "labels_received": len(view_receive_entries),
            "purchase_lines_received": len(view_purchase_keys),
            "labels_traced": _round_qty(traced_summary["labels_traced"]),
            "labels_consumed": _round_qty(traced_summary["labels_consumed"]),
            "labels_open": _round_qty(traced_summary["labels_open"]),
            "branches": len([
                branch
                for branch in branches
                if branch.active
                and branch.revenue > 0
                and _branch_matches_view(branch)
                and (not view_only_consumed or branch.consumed)
            ]),
            "unallocated_revenue": _round_money(traced_summary["unallocated_revenue"]),
            "only_consumed": bool(view_only_consumed),
            **outbound["summary"],
        }
        companies = []
        for row in company_summaries.values():
            row["gross_income"] = _round_money(row["gross_income"])
            row["gross_income_labels"] = _round_money(row["gross_income_labels"])
            row["gross_income_purchase_lines"] = _round_money(row["gross_income_purchase_lines"])
            row["labels"] = _round_qty(row["labels"])
            row["purchase_lines"] = _round_qty(row["purchase_lines"])
            row["consumed_labels"] = _round_qty(row["consumed_labels"])
            row["open_labels"] = _round_qty(row["open_labels"])
            companies.append(row)
        companies_by_code = {row["company"]: row for row in companies}
        for outbound_company in outbound["companies"]:
            code = outbound_company["company"]
            row = companies_by_code.setdefault(
                code,
                {
                    "company": code,
                    "gross_income": 0.0,
                    "gross_income_labels": 0.0,
                    "gross_income_purchase_lines": 0.0,
                    "labels": 0.0,
                    "purchase_lines": 0.0,
                    "consumed_labels": 0.0,
                    "open_labels": 0.0,
                },
            )
            for key, value in outbound_company.items():
                if key != "company":
                    row[key] = value
        companies = list(companies_by_code.values())
        companies.sort(key=lambda item: item["company"])
        return {
            "summary": summary,
            "companies": companies,
            "nodes": [*nodes, *outbound["nodes"]],
            "links": [*links, *outbound["links"]],
            "processes": processes,
            "outbound_metrics": outbound["metrics"],
            "trace_rows": [*trace_rows, *outbound["trace_rows"]],
            "period": _view_period(view_period_type, view_period_start, view_period_end),
            "filters": {
                "company": view_company_filter,
                "only_consumed": bool(view_only_consumed),
            },
        }

    current_view_company = normalized_company_filter if normalized_company_filter and normalized_company_filter != "ALL" else "ALL"
    view_payload = _build_view_payload(
        bool(only_consumed),
        warnings_out,
        view_company_filter=current_view_company,
        view_period_type=requested_period_type,
        view_period_start=period_start,
        view_period_end=period_end,
        trace_detail=True,
    )
    available_companies = sorted({branch.company for branch in branches if branch.company} | set(all_company_codes))
    if current_view_company != "ALL":
        client_companies = [current_view_company]
    else:
        client_companies = ["ALL", *available_companies]
    client_period_specs = _client_filter_period_specs(
        requested_period_type,
        period_start,
        period_end,
    )
    source_row_count = sum(len(rows or []) for rows in source_rows.values())
    estimated_client_views = len(client_period_specs) * len(client_companies) * 2
    interactive_period = requested_period_type in {"day", "week", "month"}
    prebuild_client_filters = (
        (interactive_period or source_row_count <= CLIENT_FILTER_PREBUILD_MAX_SOURCE_ROWS)
        and estimated_client_views <= CLIENT_FILTER_PREBUILD_MAX_VIEWS
    )
    alternate_key = "all" if only_consumed else "only_consumed"
    alternate_payload = None
    if prebuild_client_filters:
        alternate_payload = _build_view_payload(
            not bool(only_consumed),
            list(warnings_out),
            view_company_filter=current_view_company,
            view_period_type=requested_period_type,
            view_period_start=period_start,
            view_period_end=period_end,
            trace_detail=bool(only_consumed),
        )

    client_views: dict[str, dict] = {}
    if prebuild_client_filters:
        for view_period_type, view_period_start, view_period_end in client_period_specs:
            for view_company in client_companies:
                for view_only_consumed in (False, True):
                    key = _client_filter_view_key(view_period_type, view_period_start, view_company, view_only_consumed)
                    if key in client_views:
                        continue
                    client_views[key] = _build_view_payload(
                        view_only_consumed,
                        list(warnings_out),
                        view_company_filter=view_company,
                        view_period_type=view_period_type,
                        view_period_start=view_period_start,
                        view_period_end=view_period_end,
                        trace_detail=False,
                    )

    unique_warnings: list[dict] = []
    seen_warnings: set[tuple] = set()
    for warning in warnings_out:
        key = (
            warning.get("code"),
            warning.get("company"),
            warning.get("process_key"),
            warning.get("origin_id"),
            warning.get("message"),
        )
        if key in seen_warnings:
            continue
        seen_warnings.add(key)
        unique_warnings.append(warning)

    client_filters = {
        "schema": "views_v1",
        "views": client_views,
        "prebuilt": prebuild_client_filters,
        "estimated_views": estimated_client_views,
        "source_rows": source_row_count,
    }
    if alternate_payload is not None:
        client_filters[alternate_key] = alternate_payload
    if not prebuild_client_filters:
        client_filters["omitted_reason"] = "too_many_views" if estimated_client_views > CLIENT_FILTER_PREBUILD_MAX_VIEWS else "large_payload"

    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "period": _view_period(requested_period_type, period_start, period_end),
        "filters": {
            "company": current_view_company,
            "only_consumed": bool(only_consumed),
        },
        "schema_version": SANKEY_INBOUND_PAYLOAD_SCHEMA,
        "currency": "SEK",
        **view_payload,
        "client_filters": client_filters,
        "warnings": unique_warnings[:100],
        "source_status": list(source_status or []),
    }
