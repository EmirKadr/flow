"""CLI for Bemanning API operations.

Examples:
  python -m tools.bemanning_cli --base-url http://127.0.0.1:8000 auth login --username admin --password admin123
  python -m tools.bemanning_cli routes --format markdown
  python -m tools.bemanning_cli call schedule.get --query year=2026 --query week=21 --query weekday=1
  python -m tools.bemanning_cli api GET /api/health
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from string import Formatter
from typing import Any

import requests

from core.app_info import SERVER_BASE_URL


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COOKIE_JAR = ROOT / ".bemanning-cli-cookies.txt"


@dataclass(frozen=True)
class ApiRoute:
    name: str
    method: str
    path: str
    description: str


ROUTES: tuple[ApiRoute, ...] = (
    ApiRoute("health", "GET", "/api/health", "Server health"),
    ApiRoute("auth.login", "POST", "/api/auth/login", "Logga in"),
    ApiRoute("auth.logout", "POST", "/api/auth/logout", "Logga ut"),
    ApiRoute("auth.me", "GET", "/api/auth/me", "Aktuell användare"),
    ApiRoute("auth.set_password", "POST", "/api/auth/set-password", "Sätt första lösenord"),
    ApiRoute("allocation.health", "GET", "/api/allokering/health", "Lagerverktyg health"),
    ApiRoute("allocation.flows", "GET", "/api/allokering/flows", "Lista lagerverktygsflöden"),
    ApiRoute("allocation.pool", "GET", "/api/allokering/pool", "Lista lagerverktygens uppladdningsslots"),
    ApiRoute("allocation.detect", "POST", "/api/allokering/detect", "Identifiera lagerverktygsfil"),
    ApiRoute("allocation.observations_update", "POST", "/api/allokering/observations/update", "Uppdatera observations från buffert"),
    ApiRoute("allocation.run_flow", "POST", "/api/allokering/flow/{flow_id}", "Kör lagerverktygsflöde"),
    ApiRoute("allocation.open_excel", "POST", "/api/allokering/open-excel", "Öppna lagerverktygsresultat i Excel"),
    ApiRoute("allocation.table_column", "GET", "/api/allokering/table-column/{session_id}/{key}/{column_index}", "Hämta resultatkolumn"),
    ApiRoute("allocation.download", "GET", "/api/allokering/download/{session_id}/{key}", "Ladda ner Allokering-resultat"),
    ApiRoute("areas.list", "GET", "/api/areas", "Lista områden"),
    ApiRoute("areas.create", "POST", "/api/areas", "Skapa område"),
    ApiRoute("areas.update", "PUT", "/api/areas/{area_id}", "Uppdatera område"),
    ApiRoute("activities.list", "GET", "/api/activities", "Lista aktiviteter"),
    ApiRoute("activities.import_template", "GET", "/api/activities/import-template", "Hämta importmall för ställen"),
    ApiRoute("activities.import", "POST", "/api/activities/import", "Importera ställen"),
    ApiRoute("activities.create", "POST", "/api/activities", "Skapa aktivitet"),
    ApiRoute("activities.update", "PUT", "/api/activities/{activity_id}", "Uppdatera aktivitet"),
    ApiRoute("activities.delete", "DELETE", "/api/activities/{activity_id}", "Inaktivera aktivitet"),
    ApiRoute("settings.get", "GET", "/api/settings", "Hämta inställningar"),
    ApiRoute("settings.update", "PUT", "/api/settings", "Uppdatera inställningar"),
    ApiRoute("settings.sidebar_get", "GET", "/api/settings/sidebar", "Hämta global sidomeny"),
    ApiRoute("settings.sidebar_update", "PUT", "/api/settings/sidebar", "Uppdatera global sidomeny"),
    ApiRoute("settings.role_access_get", "GET", "/api/settings/role-access", "Hämta rollernas vyåtkomst"),
    ApiRoute("settings.role_access_update", "PUT", "/api/settings/role-access", "Uppdatera rollernas vyåtkomst"),
    ApiRoute("audit.list", "GET", "/api/audit", "Lista auditlogg"),
    ApiRoute("audit.summary", "GET", "/api/audit/summary", "Audit-summering"),
    ApiRoute("persons.list", "GET", "/api/persons", "Lista personer"),
    ApiRoute("persons.import_template", "GET", "/api/persons/import-template", "Hämta importmall för personer"),
    ApiRoute("persons.import", "POST", "/api/persons/import", "Importera personer"),
    ApiRoute("persons.create", "POST", "/api/persons", "Skapa person"),
    ApiRoute("persons.get", "GET", "/api/persons/{person_id}", "Hämta person"),
    ApiRoute("persons.update", "PUT", "/api/persons/{person_id}", "Uppdatera person"),
    ApiRoute("persons.delete", "DELETE", "/api/persons/{person_id}", "Inaktivera person"),
    ApiRoute("person_schedules.get", "GET", "/api/persons/{person_id}/schedule", "Hämta veckomall"),
    ApiRoute("person_schedules.update", "PUT", "/api/persons/{person_id}/schedule", "Uppdatera veckomall"),
    ApiRoute("schedule.get", "GET", "/api/schedule", "Hämta dagsschema"),
    ApiRoute("schedule.set_cell", "PUT", "/api/schedule/cell", "Sätt schemacell"),
    ApiRoute("schedule.split_cell", "PUT", "/api/schedule/cell/split", "Dela/slå ihop schemacell"),
    ApiRoute("schedule.bulk_cells", "POST", "/api/schedule/cells", "Sätt flera schemaceller"),
    ApiRoute("schedule.restore_hours", "PUT", "/api/schedule/hours/restore", "Återställ timmar"),
    ApiRoute("schedule.summary", "GET", "/api/schedule/summary", "Schema-summering"),
    ApiRoute("schedule.copy", "POST", "/api/schedule/copy", "Kopiera dag/vecka"),
    ApiRoute("schedule.clear", "POST", "/api/schedule/clear", "Rensa schema"),
    ApiRoute("schedule.fill_from_left", "POST", "/api/schedule/fill-from-left", "Fyll från vänster"),
    ApiRoute("overview.week", "GET", "/api/overview", "Översikt vecka"),
    ApiRoute("overview.month", "GET", "/api/overview/month", "Översikt månad"),
    ApiRoute("overview.set_day", "POST", "/api/overview/day", "Sätt dag i översikt"),
    ApiRoute("overview.bulk_days", "POST", "/api/overview/days/bulk", "Sätt flera dagar i översikt"),
    ApiRoute("users.list", "GET", "/api/users", "Lista användare"),
    ApiRoute("users.import_template", "GET", "/api/users/import-template", "Hämta importmall för användare"),
    ApiRoute("users.import", "POST", "/api/users/import", "Importera användare"),
    ApiRoute("users.create", "POST", "/api/users", "Skapa användare"),
    ApiRoute("users.update", "PUT", "/api/users/{user_id}", "Uppdatera användare"),
    ApiRoute("productivity.files", "GET", "/api/productivity/files", "Produktivitetsfilstatus"),
    ApiRoute("productivity.targets", "GET", "/api/productivity/targets", "Hämta KPI-mål"),
    ApiRoute("productivity.upload", "POST", "/api/productivity/files", "Ladda upp produktivitetsfil(er)"),
    ApiRoute("productivity.upload_raw", "POST", "/api/productivity/files/raw", "Ladda upp rå produktivitetsfil"),
    ApiRoute("productivity.delete_file", "DELETE", "/api/productivity/files/{file_type}", "Ta bort produktivitetsfil"),
    ApiRoute("productivity.report", "GET", "/api/productivity", "Produktivitetsrapport"),
    ApiRoute("public.hours", "GET", "/api/public/hours", "Publika timmar för dag"),
    ApiRoute("public.hours_week", "GET", "/api/public/hours/week", "Publika timmar för vecka"),
    ApiRoute("public.persons", "GET", "/api/public/persons", "Publika FTE för dag"),
    ApiRoute("public.persons_week", "GET", "/api/public/persons/week", "Publika FTE för vecka"),
    ApiRoute("public.summary", "GET", "/api/public/summary", "Publik CSV-summering för dag"),
    ApiRoute("public.summary_week", "GET", "/api/public/summary/week", "Publik CSV-summering för vecka"),
)

ROUTES_BY_NAME = {route.name: route for route in ROUTES}


def _parse_key_value(items: list[str] | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"Förväntade nyckel=värde, fick: {item}")
        key, value = item.split("=", 1)
        parsed[key] = value
    return parsed


def _load_json_arg(value: str | None, file_path: str | None) -> Any:
    if value and file_path:
        raise SystemExit("Använd bara en av --json och --json-file")
    if file_path:
        return json.loads(Path(file_path).read_text(encoding="utf-8"))
    if value:
        return json.loads(value)
    return None


def _path_fields(path: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(path) if field}


def _format_path(path: str, values: dict[str, str]) -> str:
    required = _path_fields(path)
    missing = sorted(required - set(values))
    if missing:
        raise SystemExit(f"Saknar path-värde: {', '.join(missing)}")
    return path.format(**{key: values[key] for key in required})


def _session(cookie_jar: Path) -> requests.Session:
    session = requests.Session()
    jar = MozillaCookieJar(str(cookie_jar))
    if cookie_jar.exists():
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            jar.clear()
    session.cookies = jar
    return session


def _save_session(session: requests.Session) -> None:
    cookies = session.cookies
    if hasattr(cookies, "save"):
        Path(cookies.filename).parent.mkdir(parents=True, exist_ok=True)
        cookies.save(ignore_discard=True, ignore_expires=True)


def _request(
    *,
    session: requests.Session,
    base_url: str,
    method: str,
    path: str,
    query: dict[str, str] | None = None,
    json_body: Any = None,
    form: dict[str, str] | None = None,
    files: Any = None,
    raw_file: str | None = None,
) -> requests.Response:
    url = base_url.rstrip("/") + path
    data = None
    if raw_file:
        data = Path(raw_file).read_bytes()
    elif form:
        data = form
    return session.request(
        method.upper(),
        url,
        params=query or None,
        json=json_body,
        data=data,
        files=files or None,
        timeout=(8, 180),
    )


def _open_files(items: list[str] | None) -> list[tuple[str, Any]]:
    opened: list[tuple[str, Any]] = []
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"Förväntade field=path, fick: {item}")
        field, path = item.split("=", 1)
        opened.append((field, open(path, "rb")))
    return opened


def _print_response(response: requests.Response, output: str | None = None) -> int:
    if output:
        Path(output).write_bytes(response.content)
    else:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        else:
            sys.stdout.buffer.write(response.content)
            if response.content and not response.content.endswith(b"\n"):
                print()
    return 0 if response.ok else 1


def _run_call(args: argparse.Namespace) -> int:
    route = ROUTES_BY_NAME[args.route]
    session = _session(args.cookie_jar)
    files = _open_files(args.file)
    try:
        path = _format_path(route.path, _parse_key_value(args.path_value))
        response = _request(
            session=session,
            base_url=args.base_url,
            method=route.method,
            path=path,
            query=_parse_key_value(args.query),
            json_body=_load_json_arg(args.json, args.json_file),
            form=_parse_key_value(args.form),
            files=files,
            raw_file=args.raw_file,
        )
        _save_session(session)
        return _print_response(response, args.output)
    finally:
        for _, file_handle in files:
            file_handle.close()


def _run_api(args: argparse.Namespace) -> int:
    session = _session(args.cookie_jar)
    files = _open_files(args.file)
    try:
        response = _request(
            session=session,
            base_url=args.base_url,
            method=args.method,
            path=args.path,
            query=_parse_key_value(args.query),
            json_body=_load_json_arg(args.json, args.json_file),
            form=_parse_key_value(args.form),
            files=files,
            raw_file=args.raw_file,
        )
        _save_session(session)
        return _print_response(response, args.output)
    finally:
        for _, file_handle in files:
            file_handle.close()


def _run_auth(args: argparse.Namespace) -> int:
    session = _session(args.cookie_jar)
    if args.auth_command == "login":
        response = _request(
            session=session,
            base_url=args.base_url,
            method="POST",
            path="/api/auth/login",
            json_body={"username": args.username, "password": args.password},
        )
    elif args.auth_command == "logout":
        response = _request(session=session, base_url=args.base_url, method="POST", path="/api/auth/logout")
        session.cookies.clear()
    elif args.auth_command == "me":
        response = _request(session=session, base_url=args.base_url, method="GET", path="/api/auth/me")
    else:
        response = _request(
            session=session,
            base_url=args.base_url,
            method="POST",
            path="/api/auth/set-password",
            json_body={"password": args.password},
        )
    _save_session(session)
    return _print_response(response, getattr(args, "output", None))


def _run_routes(args: argparse.Namespace) -> int:
    routes = [asdict(route) for route in ROUTES]
    if args.format == "json":
        print(json.dumps(routes, indent=2, ensure_ascii=False))
        return 0
    if args.format == "markdown":
        print("| Namn | Metod | Väg | Beskrivning |")
        print("| --- | --- | --- | --- |")
        for route in ROUTES:
            print(f"| `{route.name}` | `{route.method}` | `{route.path}` | {route.description} |")
        return 0
    width = max(len(route.name) for route in ROUTES)
    for route in ROUTES:
        print(f"{route.name:<{width}}  {route.method:<6} {route.path}  {route.description}")
    return 0


def _add_request_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--query", action="append", help="Query-param som key=value. Kan anges flera gånger.")
    parser.add_argument("--json", help="JSON-body som text.")
    parser.add_argument("--json-file", help="Läs JSON-body från fil.")
    parser.add_argument("--form", action="append", help="Formfält som key=value. Kan anges flera gånger.")
    parser.add_argument("--file", action="append", help="Multipart-fil som field=path. Kan anges flera gånger.")
    parser.add_argument("--raw-file", help="Skicka fil som rå request-body.")
    parser.add_argument("--output", help="Skriv svar till fil.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = _normalize_global_options(argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=SERVER_BASE_URL, help="API-bas, t.ex. https://stigamo.nu eller lokal proxy.")
    parser.add_argument("--cookie-jar", type=Path, default=DEFAULT_COOKIE_JAR, help="Cookiefil för inloggad session.")
    sub = parser.add_subparsers(dest="command", required=True)

    routes = sub.add_parser("routes", help="Lista alla kända API-vägar.")
    routes.add_argument("--format", choices=("table", "json", "markdown"), default="table")
    routes.set_defaults(func=_run_routes)

    call = sub.add_parser("call", help="Anropa en namngiven API-väg.")
    call.add_argument("route", choices=sorted(ROUTES_BY_NAME))
    call.add_argument("--path", dest="path_value", action="append", help="Path-värde som key=value.")
    _add_request_options(call)
    call.set_defaults(func=_run_call)

    api = sub.add_parser("api", help="Anropa valfri API-väg manuellt.")
    api.add_argument("method")
    api.add_argument("path")
    _add_request_options(api)
    api.set_defaults(func=_run_api)

    auth = sub.add_parser("auth", help="Inloggning och session.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_sub.add_parser("login")
    login.add_argument("--username", required=True)
    login.add_argument("--password", required=True)
    login.set_defaults(func=_run_auth)
    logout = auth_sub.add_parser("logout")
    logout.set_defaults(func=_run_auth)
    me = auth_sub.add_parser("me")
    me.set_defaults(func=_run_auth)
    set_password = auth_sub.add_parser("set-password")
    set_password.add_argument("--password", required=True)
    set_password.set_defaults(func=_run_auth)
    return parser.parse_args(argv)


def _normalize_global_options(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None
    moved: list[str] = []
    rest: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in {"--base-url", "--cookie-jar"} and index + 1 < len(argv):
            moved.extend([item, argv[index + 1]])
            index += 2
            continue
        if item.startswith("--base-url=") or item.startswith("--cookie-jar="):
            moved.append(item)
            index += 1
            continue
        rest.append(item)
        index += 1
    return moved + rest


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
