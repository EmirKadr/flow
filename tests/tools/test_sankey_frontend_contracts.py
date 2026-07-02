from pathlib import Path
from tools.frontend_sources import (
    read_overview_frontend,
    read_persons_frontend,
    read_productivity_overview_frontend,
    read_sankey_inbound_frontend,
)


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "app" / "frontend"


def test_sankey_inbound_frontend_contract():
    html = (FRONTEND / "sankey-inbound.html").read_text(encoding="utf-8")
    script = read_sankey_inbound_frontend()
    productivity = read_productivity_overview_frontend()
    sidebar = (FRONTEND / "js" / "common" / "sidebar.js").read_text(encoding="utf-8")

    assert "/js/sankey_inbound.js" in html
    assert 'data-staffing-tab-view="sankeyInbound"' in html
    assert 'class="staffing-tab active" href="/sankey-inbound.html" aria-current="page" data-staffing-tab-view="sankeyInbound"' in html
    assert "sankey-split-maps" in html
    assert 'initPage("sankeyInbound")' in script
    assert 'api.get("/api/sankey/inbound" + query' in script
    assert "sankeyNodePrimaryValue" in script
    assert "node.revenue || node.value" not in script
    assert "Statuspott" in script
    assert "Flödespott" in script
    assert "purchase_lines_received" in script
    assert "gross_income_purchase_lines" in script
    assert "purchase_line_revenue" in script
    assert "trace_rows" not in script
    assert "trace_token" in script
    assert "trace_counts" in script
    assert "trace_filter" in script
    assert "appendSankeyTraceFilterParams" in script
    assert 'params.set("start_date", filter.start_date)' in script
    assert 'params.set("only_consumed", "true")' in script
    assert 'api.get(`/api/sankey/inbound/trace?' in script
    assert 'window.location.href = `/api/sankey/inbound/trace.csv?' in script
    assert "renderSankeyTracePlaceholder" in script
    assert "hydrateSankeyTracePreview" in script
    assert "data-sankey-trace-body" in script
    assert "client_filters" in script
    assert "client-filter-v4" in script
    assert "sankeyClientViewKey" in script
    assert "sankeyPayloadForClientState" in script
    assert "sankeyPayloadForConsumedState" in script
    assert "renderSankeyCurrentView" in script
    assert "sankeySplitMaps" in script
    assert "sankey-flow-map-inbound" in script
    assert "sankey-flow-map-outbound" in script
    assert "Sankey - Outbound" in script
    assert "sankeyDisplayText" in script
    assert '["Ã¥", "å"]' in script
    assert "origin_pall" in script
    assert "current_pall" in script
    assert "sankeyTraceRowsToCsv" not in script
    assert "data-sankey-export-traces" in script
    assert "outbound_metrics" in script
    assert "Outboundintäkt" in script
    assert "outbound_picked_orders" in script
    assert "Mottagna inköpsrader" in script
    assert "Inköpsradsintäkt" in script
    assert "Visa endast förverkade" in html
    assert "Exportera spårning" in html
    assert "Sankey - Inbound" in productivity
    assert 'canViewPage(productivityOverviewUser, "sankeyInbound")' in productivity
    assert "/sankey-inbound.html" in productivity
    assert 'data-sidebar-view-id="${escapeHtml(page.id || "")}"' in sidebar
    assert "openSidebarProductivityContextMenu" in sidebar
    assert 'canViewPage(user, "sankeyInbound")' in sidebar
    assert "/sankey-inbound.html" in sidebar
