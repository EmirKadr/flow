"""Kontrakt för tools/stamp_asset_versions.py: Docker-byggets stämpling måste
täcka varje lokal script/link-tagg i frontend-HTML, annars serveras filen med
no-cache i produktion och immutable-vinsten uteblir tyst."""
import re
from pathlib import Path

from tools.stamp_asset_versions import _ASSET_TAG_RE, stamp_frontend, stamp_html

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "app" / "frontend"


def test_stamp_html_adds_content_hash(tmp_path):
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "app.js").write_bytes(b"console.log(1);")
    html = '<script src="/js/app.js"></script>'

    stamped, errors = stamp_html(html, tmp_path, "test.html")

    assert errors == []
    match = re.search(r'src="/js/app\.js\?v=([0-9a-f]{10})"', stamped)
    assert match, stamped


def test_stamp_html_replaces_existing_manual_label(tmp_path):
    (tmp_path / "css").mkdir()
    (tmp_path / "css" / "styles.css").write_bytes(b"body{}")
    html = '<link rel="stylesheet" href="/css/styles.css?v=20260701-manuell" />'

    stamped, errors = stamp_html(html, tmp_path, "test.html")

    assert errors == []
    assert "20260701-manuell" not in stamped
    assert re.search(r'href="/css/styles\.css\?v=[0-9a-f]{10}"', stamped)


def test_stamp_html_is_idempotent(tmp_path):
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "app.js").write_bytes(b"console.log(1);")
    html = '<script src="/js/app.js"></script>'

    once, _ = stamp_html(html, tmp_path, "test.html")
    twice, _ = stamp_html(once, tmp_path, "test.html")

    assert once == twice


def test_stamp_html_reports_missing_target_file(tmp_path):
    html = '<script src="/js/finns-inte.js"></script>'

    stamped, errors = stamp_html(html, tmp_path, "test.html")

    assert stamped == html
    assert errors and "finns-inte.js" in errors[0]


def test_stamp_frontend_check_mode_flags_unstamped_dir(tmp_path):
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "app.js").write_bytes(b"console.log(1);")
    (tmp_path / "index.html").write_text('<script src="/js/app.js"></script>', encoding="utf-8")

    assert stamp_frontend(tmp_path, check_only=True) == 1
    assert stamp_frontend(tmp_path, check_only=False) == 0
    assert stamp_frontend(tmp_path, check_only=True) == 0


def test_all_real_frontend_asset_tags_are_stampable():
    """Varje lokal .js/.css-referens i riktiga HTML-sidor måste träffas av
    stämplingsregexen och peka på en fil som finns. En tagg som skrivs med
    annan citatstil, eller pekar på en borttagen fil, ska fånga bygget här —
    inte upptäckas som en no-cache-fil i produktion."""
    raw_reference_re = re.compile(r"""(?:src|href)=["'](/[^"']+\.(?:js|css))(?:\?[^"']*)?["']""")
    for html_file in sorted(FRONTEND_DIR.glob("*.html")):
        html = html_file.read_text(encoding="utf-8")
        raw_refs = set(raw_reference_re.findall(html))
        stamped, errors = stamp_html(html, FRONTEND_DIR, html_file.name)

        assert errors == [], f"{html_file.name}: {errors}"
        stamped_refs = {m.group("path") for m in _ASSET_TAG_RE.finditer(stamped)}
        assert raw_refs == stamped_refs, (
            f"{html_file.name}: taggar som stämplingen missar: {raw_refs - stamped_refs}"
        )
        assert not re.search(r'(?:src|href)="/[^"?]+\.(?:js|css)"', stamped), (
            f"{html_file.name}: ostämplade taggar kvar efter stämpling"
        )
