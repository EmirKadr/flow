"""Karakterisering + guardrail for KPI-regelpredikatet (_rule_predicate).

Predikatet slar upp Fran/Till/Lokation/SSCC ur varje loggrad. De uppslagen ar
LATA: de gors bara nar regeln faktiskt har motsvarande kriterier (kandidat #40).
Gaten sitter i fyra ``need_*``-flaggor som maste hallas i synk med predikatets
grenar for hand - och en for snav flagga ger TYST fel utfall (vardet blir "",
regeln matchar ingenting) utan att nagon annan test rodnar.

Darfor listar den har filen INTE kriterienycklarna. Den HARLEDER dem ur
``_rule_predicate`` (AST) och kraver:

1. att varje gren som laser ett gate:at varde ar tackt av just det vardets gate
   (``test_varje_gren_taecks_av_sin_gate``) - detta ar det som gor att en framtida
   13:e kriterienyckel INTE kan glomma sin need_*-flagga,
2. att varje harledd kriterienyckel har bade ett runtime-uppslagstest och en rad
   i sanningstabellen (``test_alla_harledda_kriterier_*``), sa en ny nyckel inte
   kan smita forbi den beteendemassiga tackningen heller,
3. att gaten faktiskt finns kvar (spion pa ``_row_text``).

Punkt 1 ar det barande. Ett test som RAKNAR UPP tolv kriterier beskriver koden;
det skyddar den inte.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import datetime, timezone
from typing import Any

import pytest

# Monkeypatcha implementationsmodulen, inte fasaden (AGENTS.md, arkitekturkontrakt).
from app.backend.productivity_kpi_rules import rules as kpi_rules

# ---------------------------------------------------------------------------
# Harledning ur regeldefinitionen (AST over _rule_predicate)
# ---------------------------------------------------------------------------
# Vi laser tre saker ur funktionen:
#
#   kriterievariabel   loc_from_starts = _split_rule_values(_row_config_value(row, "loc_from_starts", ...))
#   gate-variabel      need_loc_from   = bool(loc_from_equals or loc_from_starts or ...)
#   lat uppslag        loc_from        = _row_text(event.row, "Fran", ...) if need_loc_from else ""
#
# ...och sedan varje ``if``-gren i predikatet som laser ett lat varde. Invarianten
# ar: alla kriterievariabler som forekommer i en sadan gren MASTE inga i det latа
# vardets gate-uttryck. Haller det inte, ar gaten for snav.

_CONFIG_CALLS = frozenset({"_row_config_value", "_rule_bool"})
_LOOKUP_CALL = "_row_text"


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    return getattr(func, "attr", "")


def _str_args(call: ast.Call) -> tuple[str, ...]:
    return tuple(a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str))


def _referenced_names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _single_assign_target(stmt: ast.stmt) -> str | None:
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        return stmt.targets[0].id
    return None


def _parse_rule_predicate() -> tuple[ast.FunctionDef, ast.FunctionDef]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(kpi_rules._rule_predicate)))
    outer = tree.body[0]
    assert isinstance(outer, ast.FunctionDef)
    inner = next(
        (s for s in outer.body if isinstance(s, ast.FunctionDef) and s.name == "predicate"),
        None,
    )
    assert inner is not None, "_rule_predicate bygger inte langre en inre predicate()"
    return outer, inner


_OUTER, _INNER = _parse_rule_predicate()

# kriterievariabel -> konfignyckel ("loc_from_starts", "sscc_length_lt", ...)
CRITERION_KEY_BY_VAR: dict[str, str] = {}
# gate-variabel -> de kriterievariabler gaten tittar pa
_GATE_CRITERIA_BY_VAR: dict[str, frozenset[str]] = {}

for _stmt in _OUTER.body:
    _var = _single_assign_target(_stmt)
    if _var is None:
        continue
    assert isinstance(_stmt, ast.Assign)
    _cfg = [c for c in ast.walk(_stmt.value) if isinstance(c, ast.Call) and _call_name(c) in _CONFIG_CALLS]
    if _cfg:
        _keys = _str_args(_cfg[0])
        assert _keys, f"kriterievariabeln {_var} har ingen konfignyckel som strangliteral"
        CRITERION_KEY_BY_VAR[_var] = _keys[0]
    else:
        _GATE_CRITERIA_BY_VAR[_var] = frozenset(_referenced_names(_stmt.value) & set(CRITERION_KEY_BY_VAR))

# lat vardevariabel -> {"gate", "columns", "criteria"}
LAZY_LOOKUPS: dict[str, dict[str, Any]] = {}
for _stmt in _INNER.body:
    _var = _single_assign_target(_stmt)
    if _var is None:
        continue
    assert isinstance(_stmt, ast.Assign)
    _val = _stmt.value
    if not (
        isinstance(_val, ast.IfExp)
        and isinstance(_val.test, ast.Name)
        and isinstance(_val.body, ast.Call)
        and _call_name(_val.body) == _LOOKUP_CALL
    ):
        continue
    _gate = _val.test.id
    LAZY_LOOKUPS[_var] = {
        "gate": _gate,
        "columns": _str_args(_val.body),
        "criteria": _GATE_CRITERIA_BY_VAR.get(_gate, frozenset()),
    }

# (vardevariabel, grenkalla, kriterievariabler i grenen)
_LAZY_BRANCHES: list[tuple[str, str, frozenset[str]]] = []
for _node in ast.walk(_INNER):
    if not isinstance(_node, ast.If):
        continue
    _used = _referenced_names(_node.test)
    _lazy_used = _used & set(LAZY_LOOKUPS)
    if not _lazy_used:
        continue
    _crit_used = frozenset(_used & set(CRITERION_KEY_BY_VAR))
    for _lazy in sorted(_lazy_used):
        _LAZY_BRANCHES.append((_lazy, ast.unparse(_node.test), _crit_used))

# Kriterienycklar (konfignycklar) som gate:ar minst ett lat uppslag.
GATED_CRITERION_KEYS: frozenset[str] = frozenset(
    CRITERION_KEY_BY_VAR[var]
    for info in LAZY_LOOKUPS.values()
    for var in info["criteria"]
)
# Kolumnnamnstupeln per kriterienyckel (den tupel _row_text anropas med).
COLUMNS_BY_CRITERION_KEY: dict[str, tuple[str, ...]] = {
    CRITERION_KEY_BY_VAR[var]: info["columns"]
    for info in LAZY_LOOKUPS.values()
    for var in info["criteria"]
}
LAZY_LOOKUP_COLUMNS: tuple[tuple[str, ...], ...] = tuple(info["columns"] for info in LAZY_LOOKUPS.values())


# ---------------------------------------------------------------------------
# Deklarationer som en NY kriterienyckel tvingas fylla i
# ---------------------------------------------------------------------------
# Ett exempelvarde per kriterienyckel, sa den harledda nyckeln kan drivas genom
# predikatet. Lagger du till ett kriterium i _rule_predicate MASTE du lagga till
# det har - annars rodnar test_alla_harledda_kriterier_har_exempelvarde.
SAMPLE_CRITERION_VALUES: dict[str, str] = {
    "loc_from_starts": "AA",
    "loc_from_equals": "Transit",
    "loc_from_not_starts": "AA;UT",
    "loc_from_not_equals": "Transit",
    "loc_to_starts": "AS",
    "loc_to_equals": "Transit",
    "loc_to_not_starts": "AS",
    "loc_to_not_equals": "Transit",
    "location_starts": "UT",
    "location_not_starts": "UT",
    "sscc_length_lt": "12",
    "sscc_length_gte": "12",
}


def _rule(**overrides: str) -> kpi_rules.KpiRule:
    row: dict[str, str] = {"process": "TestProcess", "source": "pick", "metric": "rows"}
    row.update(overrides)
    rules = kpi_rules.parse_kpi_rule_rows([row])
    assert len(rules) == 1
    return rules[0]


def _event(row: dict[str, str], *, company: str = "", source: str = "pick") -> kpi_rules.KpiLogEvent:
    return kpi_rules.KpiLogEvent(
        source=source,
        user="ANV",
        company=company,
        warehouse="1",
        timestamp=datetime(2026, 7, 14, 8, 0, tzinfo=timezone.utc),
        row=row,
        row_index=1,
    )


def _spy_on_row_text(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Loggar namn-tupeln for varje _row_text-anrop.

    Installeras EFTER parse_kpi_rule_rows, annars smutsar factoryns egna
    _row_config_value-anrop ner listan. Fangar aven _row_number/_row_upper/
    _row_int_text (de slar upp _row_text via modulglobalen) - darfor filtrerar
    testerna pa namn-tupeln, inte pa antalet anrop.
    """
    calls: list[tuple[str, ...]] = []
    original = kpi_rules._row_text

    def spy(row: dict[str, str], *names: str) -> str:
        calls.append(names)
        return original(row, *names)

    monkeypatch.setattr(kpi_rules, "_row_text", spy)
    return calls


# ---------------------------------------------------------------------------
# 1. Sjalva forsvaret: gaten maste tacka varje gren som laser dess varde
# ---------------------------------------------------------------------------

def test_ast_harledningen_hittade_gaten() -> None:
    """Vakt mot ett tomt (och darmed meningslost) harlett underlag.

    Utan den har kontrollen skulle en refaktorering som doper om/flyttar gaten
    gora AST-testerna nedan VAKUOST GRONA: inga lata uppslag hittade -> inga
    grenar att kontrollera -> allt passerar.
    """
    assert set(LAZY_LOOKUPS) >= {"loc_from", "loc_to", "location", "sscc"}, (
        f"de fyra lata uppslagen (kandidat #40) hittades inte langre: {sorted(LAZY_LOOKUPS)}"
    )
    for name, info in LAZY_LOOKUPS.items():
        assert info["columns"], f"{name}: hittade inga kolumnnamn i _row_text-anropet"
        assert info["criteria"], f"{name}: gaten {info['gate']} tittar inte pa nagot kriterium"
    assert len(GATED_CRITERION_KEYS) >= 12, (
        f"forvantade minst de tolv kanda kriterierna, harledde {sorted(GATED_CRITERION_KEYS)}"
    )
    assert _LAZY_BRANCHES, "hittade inga grenar som laser ett gate:at varde"


def test_varje_gren_taecks_av_sin_gate() -> None:
    """GUARDRAIL: en gren som laser ett gate:at varde far bara styras av kriterier
    som INGAR i vardets gate.

    Detta ar filens karnpast. Lagger nagon till en 13:e kriterienyckel som laser
    location/loc_from/loc_to/sscc men glommer sin need_*-flagga, blir vardet tyst
    "" och regeln matchar ingenting - hela ovriga sviten forblir gron. Har rodnar
    det, utan att nagon behover minnas att uppdatera en lista.
    """
    for value_var, branch_src, criteria_in_branch in _LAZY_BRANCHES:
        info = LAZY_LOOKUPS[value_var]
        missing = criteria_in_branch - info["criteria"]
        assert not missing, (
            f"grenen `if {branch_src}` laser `{value_var}`, som bara slas upp nar "
            f"`{info['gate']}` ar sant. Men {sorted(missing)} ingar inte i "
            f"`{info['gate']}` ({sorted(info['criteria'])}) - gaten ar for snav och "
            f"regeln far tyst `{value_var} = \"\"`. Lagg till kriteriet i "
            f"`{info['gate']}` i app/backend/productivity_kpi_rules/rules.py."
        )


def test_alla_harledda_kriterier_har_exempelvarde() -> None:
    """Tvingar en ny kriterienyckel att deklarera sig for uppslagstestet nedan."""
    missing = GATED_CRITERION_KEYS - set(SAMPLE_CRITERION_VALUES)
    assert not missing, (
        f"nya kriterienycklar {sorted(missing)} saknar exempelvarde i "
        "SAMPLE_CRITERION_VALUES - lagg till dem sa uppslagstestet kan driva dem"
    )


# ---------------------------------------------------------------------------
# 2. Runtime: gaten finns kvar (negativ) och ar inte for snav (positiv)
# ---------------------------------------------------------------------------

def test_predicate_skips_loc_and_sscc_lookups_when_rule_has_no_such_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GUARDRAIL: en regel utan loc-/sscc-kriterier far inte rora de kolumnerna.

    Detta ar optimeringen (kandidat #40). Forsvinner gaten vid en framtida
    refaktorering ska detta test bli rott - inte tyst langsamt igen. Kolumnnamnen
    harleds ur _row_text-anropen, sa testet foljer med om de andras.
    """
    rule = _rule(process="Manual_Pick", zone="A", positive_column="Plockat")
    calls = _spy_on_row_text(monkeypatch)

    event = _event({"Zon": "A", "Plockat": "10"})
    # Assert:as FORST: bevisar att predikatet nadde slutet och inte tog en tidig
    # return. Utan detta vore testet gront aven pa ogate:ad kod som returnerar
    # False innan raderna med uppslagen.
    assert rule.predicate(event, {}) is True

    for columns in LAZY_LOOKUP_COLUMNS:
        assert columns not in calls, f"predikatet slog upp {columns} trots att regeln saknar det kriteriet"


@pytest.mark.parametrize(
    "criterion_key",
    sorted(GATED_CRITERION_KEYS),
)
def test_predicate_still_looks_up_loc_and_sscc_when_rule_has_criteria(
    monkeypatch: pytest.MonkeyPatch,
    criterion_key: str,
) -> None:
    """POSITIV KONTROLL: gaten far inte 'fixas' genom att uppslaget tas bort helt.

    Kriterielistan HARLEDS ur _rule_predicate - den ar inte nedskriven har. Varje
    kriterienyckel som laser ett varde maste ocksa sla upp det; testet faller om
    nagon gate blir for snav (t.ex. glommer location_not_starts).
    """
    expected_columns = COLUMNS_BY_CRITERION_KEY[criterion_key]
    rule = _rule(**{criterion_key: SAMPLE_CRITERION_VALUES[criterion_key]})
    calls = _spy_on_row_text(monkeypatch)

    rule.predicate(_event({"Zon": "A"}), {})

    assert expected_columns in calls, (
        f"kriteriet {criterion_key} laser {expected_columns} men slog aldrig upp det - "
        f"gaten for det vardet ar for snav"
    )


# (namn, regelkolumner, loggrad, forvantat predikatutfall)
# Sanningstabell over predikatets loc-/sscc-kriterier. Detta ar det enda som kan
# avsloja ett FEL gate-villkor beteendemassigt - ovriga produktivitetstester kan
# forbli grona med en trasig gate (sort-fixturerna ar tomma och den enda
# location-raden gar i den riktning dar "" och BUFF01 ger samma svar).
# Tackningen kontrolleras mot AST-harledningen i
# test_alla_harledda_kriterier_finns_i_sanningstabellen - listan far inte halka
# efter regeldefinitionen.
PREDICATE_MATRIX: tuple[tuple[str, dict[str, str], dict[str, str], bool], ...] = (
    # --- inga loc-/sscc-kriterier: "" -fallbacket far inte paverka utfallet ---
    ("no_criteria_matches", {"zone": "A", "positive_column": "Plockat"}, {"Zon": "A", "Plockat": "3"}, True),
    ("no_criteria_zero_pick", {"zone": "A", "positive_column": "Plockat"}, {"Zon": "A", "Plockat": "0"}, False),
    # --- loc_from_equals / loc_from_not_equals ---
    ("from_equals_hit", {"loc_from_equals": "Transit"}, {"Från": "Transit"}, True),
    ("from_equals_miss", {"loc_from_equals": "Transit"}, {"Fr\xc3\xa5n": "AA0101"}, False),
    ("from_equals_no_column", {"loc_from_equals": "Transit"}, {"Typ": "31"}, False),
    ("from_not_equals_blocks", {"loc_from_not_equals": "Transit"}, {"Fran": "Transit"}, False),
    ("from_not_equals_passes", {"loc_from_not_equals": "Transit"}, {"loc_from": "AA0101"}, True),
    ("from_not_equals_no_column", {"loc_from_not_equals": "Transit"}, {"Typ": "31"}, True),
    # --- loc_from_starts / loc_from_not_starts ---
    ("from_starts_hit", {"loc_from_starts": "AA"}, {"Från": "AA0101"}, True),
    ("from_starts_miss", {"loc_from_starts": "AA"}, {"Från": "BB0101"}, False),
    ("from_starts_no_column", {"loc_from_starts": "AA"}, {"Typ": "31"}, False),
    ("from_not_starts_passes", {"loc_from_not_starts": "AA;UT"}, {"Från": "BB0101"}, True),
    ("from_not_starts_blocks", {"loc_from_not_starts": "AA;UT"}, {"Från": "UT0050"}, False),
    ("from_not_starts_no_column", {"loc_from_not_starts": "AA;UT"}, {"Typ": "31"}, True),
    # --- loc_to_equals / loc_to_not_equals (noll referensregler anvander dem) ---
    ("to_equals_hit", {"loc_to_equals": "Transit"}, {"Till": "Transit"}, True),
    ("to_equals_no_column", {"loc_to_equals": "Transit"}, {"Typ": "26"}, False),
    ("to_not_equals_blocks", {"loc_to_not_equals": "Transit"}, {"Till": "Transit"}, False),
    ("to_not_equals_passes", {"loc_to_not_equals": "Transit"}, {"loc_to": "HBW01"}, True),
    ("to_not_equals_no_column", {"loc_to_not_equals": "Transit"}, {"Typ": "26"}, True),
    # --- loc_to_starts / loc_to_not_starts ---
    ("to_starts_hit", {"loc_to_starts": "AS"}, {"Till": "AS12"}, True),
    ("to_starts_miss", {"loc_to_starts": "AS"}, {"Till": "HBW01"}, False),
    ("to_starts_no_column", {"loc_to_starts": "AS"}, {"Typ": "26"}, False),
    ("to_not_starts_passes", {"loc_to_not_starts": "AS"}, {"Till": "HBW01"}, True),
    ("to_not_starts_blocks_casefold", {"loc_to_not_starts": "AS"}, {"Till": "as0101"}, False),
    ("to_not_starts_no_column", {"loc_to_not_starts": "AS"}, {"Typ": "26"}, True),
    # --- location_starts / location_not_starts (Full_Pallet_From_HBW vs Full_Manual_Buffer) ---
    # Raden med Lokation=UT001 i zon H ar den som avslojar en trasig need_location:
    # med "" skulle BADA reglerna matcha samma pall = dubbelrakning.
    (
        "location_starts_ut_matches_hbw",
        {"process": "Full_Pallet_From_HBW", "metric": "pallets", "zone": "H", "location_starts": "UT", "positive_column": "Plockat"},
        {"Zon": "H", "Lokation": "UT001", "Plockat": "1"},
        True,
    ),
    (
        "location_starts_buffer_does_not_match_hbw",
        {"process": "Full_Pallet_From_HBW", "metric": "pallets", "zone": "H", "location_starts": "UT", "positive_column": "Plockat"},
        {"Zon": "H", "Lokation": "BUFF01", "Plockat": "1"},
        False,
    ),
    (
        "location_not_starts_ut_excluded_from_buffer",
        {"process": "Full_Manual_Buffer", "metric": "pallets", "zone": "H", "location_not_starts": "UT", "positive_column": "Plockat"},
        {"Zon": "H", "Lokation": "UT001", "Plockat": "1"},
        False,
    ),
    (
        "location_not_starts_buffer_matches_buffer",
        {"process": "Full_Manual_Buffer", "metric": "pallets", "zone": "H", "location_not_starts": "UT", "positive_column": "Plockat"},
        {"Zon": "H", "Lokation": "BUFF01", "Plockat": "1"},
        True,
    ),
    (
        "location_not_starts_no_column",
        {"process": "Full_Manual_Buffer", "metric": "pallets", "zone": "H", "location_not_starts": "UT", "positive_column": "Plockat"},
        {"Zon": "H", "Plockat": "1"},
        True,
    ),
    # --- sscc_length_lt / sscc_length_gte (Sort_Ecom vs Sort_Store) ---
    # Ingen befintlig test rorde sscc-grenarna alls: alla sort-fixturer ar tomma.
    (
        "sscc_short_is_ecom",
        {"process": "Sort_Ecom", "source": "sort", "metric": "pallets", "sscc_length_lt": "12"},
        {"SSCC": "1234567890"},
        True,
    ),
    (
        "sscc_long_is_not_ecom",
        {"process": "Sort_Ecom", "source": "sort", "metric": "pallets", "sscc_length_lt": "12"},
        {"SSCC": "123456789012"},
        False,
    ),
    (
        "sscc_long_is_store",
        {"process": "Sort_Store", "source": "sort", "metric": "pallets", "sscc_length_gte": "12"},
        {"SSCC": "123456789012"},
        True,
    ),
    (
        "sscc_short_is_not_store",
        {"process": "Sort_Store", "source": "sort", "metric": "pallets", "sscc_length_gte": "12"},
        {"SSCC": "1234567890"},
        False,
    ),
    (
        "sscc_alias_column_is_store",
        {"process": "Sort_Store", "source": "sort", "metric": "pallets", "sscc_length_gte": "12"},
        {"sscc": "123456789012"},
        True,
    ),
    (
        "sscc_missing_column_is_ecom",
        {"process": "Sort_Ecom", "source": "sort", "metric": "pallets", "sscc_length_lt": "12"},
        {"Pallid": "P1"},
        True,
    ),
    # --- alias-only-rad: kolumnnamnen finns bara i sina engelska alias ---
    (
        "alias_only_columns",
        {"loc_from_starts": "AA", "location_starts": "UT"},
        {"loc_from": "AA9", "location": "UT2"},
        True,
    ),
    (
        "alias_only_columns_miss",
        {"loc_from_starts": "AA", "location_starts": "UT"},
        {"loc_from": "AA9", "location": "BUFF"},
        False,
    ),
    # --- kombination: alla fyra vardena laser samma rad ---
    (
        "all_four_criteria_together",
        {
            "loc_from_starts": "AA",
            "loc_to_not_starts": "AS",
            "location_starts": "UT",
            "sscc_length_gte": "12",
        },
        {"Från": "AA01", "Till": "HBW", "Lokation": "UT9", "SSCC": "123456789012"},
        True,
    ),
    (
        "all_four_criteria_one_fails",
        {
            "loc_from_starts": "AA",
            "loc_to_not_starts": "AS",
            "location_starts": "UT",
            "sscc_length_gte": "12",
        },
        {"Från": "AA01", "Till": "HBW", "Lokation": "UT9", "SSCC": "1234567890"},
        False,
    ),
)


def test_alla_harledda_kriterier_finns_i_sanningstabellen() -> None:
    """Tvingar en ny kriterienyckel in i sanningstabellen ovan.

    Utan detta kan en 13:e nyckel laggas till med korrekt need_*-flagga men helt
    utan beteendetackning - den skulle da bara vara "deklarerad", inte provad.
    """
    covered = {key for _name, rule_row, _log_row, _expected in PREDICATE_MATRIX for key in rule_row}
    missing = GATED_CRITERION_KEYS - covered
    assert not missing, (
        f"kriterierna {sorted(missing)} saknar rad i PREDICATE_MATRIX - "
        "lagg till minst ett trafffall och ett missfall"
    )


@pytest.mark.parametrize(
    ("rule_row", "log_row", "expected"),
    [pytest.param(rule_row, log_row, expected, id=name) for name, rule_row, log_row, expected in PREDICATE_MATRIX],
)
def test_predicate_criteria_matrix(
    rule_row: dict[str, str],
    log_row: dict[str, str],
    expected: bool,
) -> None:
    """KARAKTERISERING: sanningstabell over predikatets loc-/sscc-kriterier."""
    rule = _rule(**rule_row)
    context: dict[str, Any] = {}

    assert rule.predicate(_event(log_row), context) is expected
