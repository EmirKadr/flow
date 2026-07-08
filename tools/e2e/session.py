"""FlowSession: en tunn, agent-vänlig wrapper runt en Playwright-sida.

Sköter inloggning, navigering, interaktioner, skärmbilder och DOM-/text-
extraktion, och fångar löpande konsolmeddelanden och misslyckade nätverks-
svar (4xx/5xx/failed). Konsol/nätverk kan "dräneras" per sida så scenarier
kan tillskriva fel rätt vy.

Endast Playwrights sync-API. Lösenordet skickas till login() men loggas
aldrig av den här modulen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class FlowSession:
    def __init__(self, page, out_dir: Path):
        self.page = page
        self.out_dir = out_dir
        self._console: list[dict[str, Any]] = []
        self._network: list[dict[str, Any]] = []
        page.on("console", self._on_console)
        page.on("pageerror", self._on_pageerror)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_requestfailed)

    # --- händelsefångst ---
    def _on_console(self, msg) -> None:
        try:
            level = msg.type
            if level in ("error", "warning"):
                self._console.append({"level": level, "text": str(msg.text)[:500]})
        except Exception:  # noqa: BLE001 - fångst får aldrig störa körningen
            pass

    def _on_pageerror(self, exc) -> None:
        self._console.append({"level": "error", "text": f"pageerror: {str(exc)[:500]}"})

    def _on_response(self, response) -> None:
        try:
            status = response.status
            if status >= 400:
                self._network.append({"status": status, "url": str(response.url)[:300]})
        except Exception:  # noqa: BLE001
            pass

    def _on_requestfailed(self, request) -> None:
        try:
            failure = request.failure or ""
            # net::ERR_ABORTED = requesten avbröts av navigering (beacons,
            # prefetch, SWR som hinner cancelleras). Det är inte ett riktigt
            # fel — utan filtret skulle varje körning rapportera falska larm.
            if "ERR_ABORTED" in failure:
                return
            self._network.append({"status": "failed", "url": str(request.url)[:300], "error": failure[:120]})
        except Exception:  # noqa: BLE001
            pass

    def drain_console(self) -> list[dict[str, Any]]:
        entries, self._console = self._console, []
        return entries

    def drain_network(self) -> list[dict[str, Any]]:
        entries, self._network = self._network, []
        return entries

    # --- inloggning & navigering ---
    def login(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.page.goto(f"{self.base_url}/login.html", wait_until="load")
        self.page.fill("#username", username)
        self.page.fill("#password", password)
        self.page.click("button.primary")
        self.page.wait_for_url("**/index.html", timeout=20000)
        self.page.wait_for_selector("#bug-report-toggle", timeout=20000)
        self.drain_console()   # ignorera ev. brus från inloggningsflödet
        self.drain_network()

    def goto(self, path: str, wait_until: str = "networkidle") -> float | None:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        response = self.page.goto(url, wait_until=wait_until)
        try:
            timing = self.page.evaluate(
                "() => { const t = performance.getEntriesByType('navigation')[0];"
                " return t ? Math.round(t.duration) : null; }"
            )
        except Exception:  # noqa: BLE001
            timing = None
        _ = response
        return timing

    # --- interaktioner ---
    def click(self, selector: str, timeout: int = 15000) -> None:
        self.page.click(selector, timeout=timeout)

    def fill(self, selector: str, value: str, timeout: int = 15000) -> None:
        self.page.fill(selector, value, timeout=timeout)

    def select(self, selector: str, value: str, timeout: int = 15000) -> None:
        self.page.select_option(selector, value, timeout=timeout)

    def hover(self, selector: str, timeout: int = 15000) -> None:
        self.page.hover(selector, timeout=timeout)

    def press(self, selector: str, key: str) -> None:
        self.page.press(selector, key)

    def wait(self, selector: str, timeout: int = 15000, state: str = "visible") -> None:
        self.page.wait_for_selector(selector, timeout=timeout, state=state)

    def wait_ms(self, ms: int) -> None:
        self.page.wait_for_timeout(ms)

    # --- läsning / inspektion ---
    def exists(self, selector: str) -> bool:
        return self.page.query_selector(selector) is not None

    def count(self, selector: str) -> int:
        return len(self.page.query_selector_all(selector))

    def text(self, selector: str) -> str:
        el = self.page.query_selector(selector)
        return (el.inner_text() if el else "").strip()

    def page_text(self, limit: int = 4000) -> str:
        try:
            body = self.page.inner_text("body")
        except Exception:  # noqa: BLE001
            body = ""
        return body[:limit]

    def title_path(self) -> str:
        try:
            return self.page.url.replace(self.base_url, "") or "/"
        except Exception:  # noqa: BLE001
            return "?"

    # --- skärmbilder ---
    def screenshot(self, name: str, selector: str | None = None, full_page: bool = True) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{name}.png"
        if selector:
            el = self.page.query_selector(selector)
            if el is None:
                raise ValueError(f"Selector for skarmbild saknas: {selector}")
            el.screenshot(path=str(path))
        else:
            self.page.screenshot(path=str(path), full_page=full_page)
        return path
