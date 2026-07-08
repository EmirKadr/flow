"""Outbound-delen av Sankey-bygget.

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
from .build_graph import (  # noqa: F401
    _sync_branch_revenue,
    _normalize_process_point_key,
    _process_points_from_kpi,
    _process_point_value,
    _append_process,
    _classify_trans,
    _pick_location_key,
    _consume_pick_queue,
    _branch_matches_pall,
    _event_sort_key,
    _build_current_pallet_locations,
    _status_from_current_location,
    _node_id,
    _add_node,
    _add_link,
    _trace_path_steps,
    _trace_row_for_branch,
    _minimal_trace_row,
    _finalize_sankey,
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
    package_ladders: dict | None = None,
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
    # Beräknas normalt en gång i build_sankey_inbound_payload och skickas in;
    # fallback om funktionen anropas fristående.
    if package_ladders is None:
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
