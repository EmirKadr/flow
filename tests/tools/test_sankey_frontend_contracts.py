from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "app" / "frontend"


def test_sankey_inbound_frontend_contract():
    html = (FRONTEND / "sankey-inbound.html").read_text(encoding="utf-8")
    script = (FRONTEND / "js" / "sankey_inbound.js").read_text(encoding="utf-8")
    productivity = (FRONTEND / "js" / "productivity_overview.js").read_text(encoding="utf-8")
    sidebar = (FRONTEND / "js" / "common" / "sidebar.js").read_text(encoding="utf-8")

    assert "/js/sankey_inbound.js" in html
    assert 'initPage("sankeyInbound")' in script
    assert 'api.get("/api/sankey/inbound" + query' in script
    assert "sankeyNodePrimaryValue" in script
    assert "node.revenue || node.value" not in script
    assert "Statuspott" in script
    assert "Flödespott" in script
    assert "purchase_lines_received" in script
    assert "gross_income_purchase_lines" in script
    assert "purchase_line_revenue" in script
    assert "Mottagna inköpsrader" in script
    assert "Inköpsradsintäkt" in script
    assert "Visa endast förverkade" in html
    assert "Sankey - Inbound" in productivity
    assert 'canViewPage(productivityOverviewUser, "sankeyInbound")' in productivity
    assert "/sankey-inbound.html" in productivity
    assert 'data-sidebar-view-id="${escapeHtml(page.id || "")}"' in sidebar
    assert "openSidebarProductivityContextMenu" in sidebar
    assert 'canViewPage(user, "sankeyInbound")' in sidebar
    assert "/sankey-inbound.html" in sidebar
