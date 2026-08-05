"""Kontrakt: flytande ytor placeras i rätt koordinatrymd när appzoom är på.

Appzoomen sätts som `zoom` på <body> (theme.js) och ärvs av alla ättlingar,
även `position: fixed`-menyer som ligger direkt under body. `clientX/clientY`
och `getBoundingClientRect()` mäts i viewportens skala, medan `style.left/top`
tolkas i elementets egen (zoomade) skala. Skriver man ett viewport-värde rakt
in i `style.left` hamnar menyn `zoom` gånger för nära origo — vid 70 % dök
bemanningsvyns högerklicksmeny upp uppe till vänster om pekaren i stället för
vid den (rapporterat 2026-08-04).

Testet är statiskt så det ingår i `npm run test:fast`/pre-push: varje beräknad
px-skrivning till `style.left/top` måste gå via omräknarna i theme.js, annars
måste filen stå med i undantagslistan med ett motiv.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_ROOT = ROOT / "app" / "frontend" / "js"

HELPERS = ("positionElementAtViewportPoint", "viewportPxToElementPx", "effectiveCssZoom")

# Filer som skriver style.left/top i en koordinatrymd som redan är elementets
# egen — de ska inte räknas om en gång till.
LOCAL_SPACE_FILES = {
    "common/theme.js": "definierar själva omräknarna",
    "allocation/map_settings.js": "räknar redan om med workspace.clientWidth/rect-kvoten",
    "label_editor/editor.js": "mm→px i etikettytans egen skala",
    "schedule/rfid.js": "procentplacering inuti cellen, inte viewport-px",
    "schedule/summary.js": "host-relativ meny; räknar om varje mätning med viewportPxToElementPx",
}

# Konstanta värden är alltid ofarliga: de beror inte på en viewport-mätning.
CONSTANT_VALUE = re.compile(r"""^\s*=\s*["'][^"']*["']\s*;?\s*$""")
STYLE_ASSIGNMENT = re.compile(r"\.style\.(?:left|top)\s*(=[^\n]*)")


def _js_files() -> list[Path]:
    return [
        path
        for path in sorted(JS_ROOT.rglob("*.js"))
        if "vendor" not in path.relative_to(JS_ROOT).parts
    ]


def test_computed_menu_positions_go_through_the_zoom_helpers():
    offenders = []
    for path in _js_files():
        rel = path.relative_to(JS_ROOT).as_posix()
        if rel in LOCAL_SPACE_FILES:
            continue
        source = path.read_text(encoding="utf-8")
        for number, line in enumerate(source.splitlines(), start=1):
            match = STYLE_ASSIGNMENT.search(line)
            if not match or CONSTANT_VALUE.match(match.group(1)):
                continue
            offenders.append(f"{rel}:{number}: {line.strip()}")
    assert offenders == [], (
        "Beräknad style.left/top utan zoomomräkning — använd "
        "positionElementAtViewportPoint()/viewportPxToElementPx() från "
        "common/theme.js, eller lägg filen i LOCAL_SPACE_FILES med motiv:\n"
        + "\n".join(offenders)
    )


def test_zoom_helpers_live_in_the_shared_common_layer():
    """Hjälparna måste ligga i common/ — domänsidorna laddar bara common + en
    domänkatalog, så en domänplacering hade gjort dem onåbara för de andra."""
    theme = (JS_ROOT / "common" / "theme.js").read_text(encoding="utf-8")
    for helper in HELPERS:
        assert f"function {helper}(" in theme, f"{helper} saknas i common/theme.js"


def test_local_space_exceptions_still_exist():
    """En undantagsfil som splittats eller döpts om ska tas bort ur listan i
    samma arbetsinsats, annars tystar undantaget en fil som inte finns."""
    missing = [rel for rel in LOCAL_SPACE_FILES if not (JS_ROOT / rel).exists()]
    assert missing == [], f"Undantag pekar på filer som inte finns: {missing}"
