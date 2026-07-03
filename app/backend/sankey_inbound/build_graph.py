"""Grafprimitiver for Sankey-bygget: noder, lankar, trace-rader och finalize.

Utdelat ur sankey_inbound/build.py for radtaket i arkitektur-kontraktet.
"""
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
