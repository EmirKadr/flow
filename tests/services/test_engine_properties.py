"""Property-baserade tester (Hypothesis) för engine_core:s rena funktioner.

Golden-testerna låser beteendet för FASTA indata; de här attackerar med
genererade. Egenskaper i stället för exempel: "utdata innehåller aldrig
'nan'", "summan av chunks == indata", "web och desktop delar identiskt".
Pandas 3-buggen (NaN -> "nan" i Plockplats) hade fångats här.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest
from hypothesis import assume, given, settings, strategies as st

from warehouse_tools.engine_core.io_utils import normalize_saldo
from warehouse_tools.engine_core.reports import build_chunked_values_result
from warehouse_tools.native_flows import _chunk_values

# Värden som de förekommer i verkliga inklistringar: ordernummer, artiklar,
# whitespace-skräp och unicode. Kontrollen exkluderar radbrytningar eftersom
# indata redan är radsplittad när funktionerna får den.
value_text = st.text(
    alphabet=st.characters(exclude_characters="\r\n", exclude_categories=("Cs",)),
    min_size=0,
    max_size=20,
)


@settings(max_examples=100, deadline=None)
@given(values=st.lists(value_text, min_size=1, max_size=120), chunk_size=st.integers(min_value=1, max_value=50))
def test_chunked_values_preserve_every_value_in_order(values, chunk_size):
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    if not cleaned:
        with pytest.raises(ValueError):
            build_chunked_values_result(values, chunk_size)
        return

    result = build_chunked_values_result(values, chunk_size)

    assert result.value_count == len(cleaned)
    assert result.chunk_count == math.ceil(len(cleaned) / chunk_size)
    # Konkatenerade kolumner (utan padding) == rensade värden i samma ordning.
    reassembled: list[str] = []
    for column in result.report_df.columns:
        reassembled.extend(v for v in result.report_df[column].tolist() if v != "")
    # Padding-filtret ovan tar även bort äkta tomma värden - men cleaned
    # innehåller per definition inga tomma strängar, så jämförelsen är exakt.
    assert reassembled == cleaned
    # Ingen kolumn får överskrida chunk_size.
    for column in result.report_df.columns:
        non_padding = [v for v in result.report_df[column].tolist() if v != ""]
        assert len(non_padding) <= chunk_size


@settings(max_examples=50, deadline=None)
@given(chunk_size=st.one_of(st.integers(max_value=0), st.just("abc")))
def test_chunked_values_reject_invalid_chunk_size(chunk_size):
    with pytest.raises(ValueError):
        build_chunked_values_result(["a", "b"], chunk_size)


@settings(max_examples=100, deadline=None)
@given(
    values=st.lists(value_text.filter(lambda s: s.strip()), min_size=1, max_size=120),
    chunk_size=st.integers(min_value=1, max_value=50),
)
def test_split_values_web_and_desktop_partition_identically(values, chunk_size):
    """Paritetsregeln (AGENTS.md) som egenskap: webbens motor och desktopens
    native-flöde måste dela samma värden i exakt samma kolumner."""
    cleaned = [str(v).strip() for v in values]

    engine_result = build_chunked_values_result(cleaned, chunk_size)
    native_table = _chunk_values(cleaned, chunk_size)

    expected_chunks = [cleaned[i: i + chunk_size] for i in range(0, len(cleaned), chunk_size)]

    engine_chunks = [
        [v for v in engine_result.report_df[column].tolist() if v != ""]
        for column in engine_result.report_df.columns
    ]
    native_chunks = [
        [row[col_index] for row in native_table.rows if row[col_index] != ""]
        for col_index in range(len(native_table.columns))
    ]
    assert engine_chunks == expected_chunks
    assert native_chunks == expected_chunks
    assert list(engine_result.report_df.columns) == native_table.columns


article_text = st.text(alphabet="ABC123- ", min_size=1, max_size=8).filter(lambda s: s.strip())
saldo_value = st.one_of(st.integers(min_value=0, max_value=10_000), st.none())
plats_value = st.one_of(st.none(), st.just(""), st.just("  "), st.text(alphabet="A-19 ", max_size=6))


@settings(max_examples=100, deadline=None)
@given(rows=st.lists(st.tuples(article_text, saldo_value, plats_value), min_size=1, max_size=40))
def test_normalize_saldo_never_leaks_nan_and_sums_per_article(rows):
    df = pd.DataFrame(
        {
            "Artikel": [article for article, _saldo, _plats in rows],
            "Plocksaldo": [saldo for _article, saldo, _plats in rows],
            "Plockplats": [plats for _article, _saldo, plats in rows],
        },
        dtype=object,
    )

    result = normalize_saldo(df)

    assert list(result.columns) == ["Artikel", "Plocksaldo", "Plockplats"]
    # Regressionen fran pandas-bumpen: NaN far aldrig bli strangen "nan".
    assert not result["Plockplats"].astype(str).str.fullmatch(r"nan|none|nan\.0", case=False).any()
    # En rad per unik (trimmad) artikel.
    trimmed_articles = {article.strip() for article, _saldo, _plats in rows}
    assert set(result["Artikel"]) == trimmed_articles
    assert len(result) == len(trimmed_articles)
    # Plocksaldo ar summan per artikel (None raknas som 0).
    for article in trimmed_articles:
        expected = sum(
            saldo or 0 for raw_article, saldo, _plats in rows if raw_article.strip() == article
        )
        actual = float(result.loc[result["Artikel"] == article, "Plocksaldo"].iloc[0])
        assert actual == pytest.approx(float(expected))
    # Plockplats ar forsta icke-tomma platsen per artikel.
    for article in trimmed_articles:
        expected_plats = next(
            (
                str(plats).strip()
                for raw_article, _saldo, plats in rows
                if raw_article.strip() == article and plats is not None and str(plats).strip()
            ),
            "",
        )
        actual_plats = result.loc[result["Artikel"] == article, "Plockplats"].iloc[0]
        assert actual_plats == expected_plats


# ---------------------------------------------------------------------------
# to_num: total funktion — kraschar aldrig, returnerar alltid ändlig float,
# och tolkar svensk sifferform (mellanslag som tusentalsavgränsare, komma
# som decimaltecken) exakt. (Nattpass 2026-07-07.)
# ---------------------------------------------------------------------------


@given(
    st.one_of(
        st.none(),
        st.text(max_size=30),
        st.floats(allow_nan=True, allow_infinity=False, width=32),
        st.integers(min_value=-(10**9), max_value=10**9),
    )
)
@settings(max_examples=200, deadline=None)
def test_to_num_is_total_and_finite(value):
    from warehouse_tools.engine_core.io_utils import to_num

    result = to_num(value)
    assert isinstance(result, float)
    assert math.isfinite(result)


@given(
    st.integers(min_value=-(10**9), max_value=10**9),
    st.integers(min_value=0, max_value=99),
)
@settings(max_examples=100, deadline=None)
def test_to_num_parses_swedish_number_format(whole, decimals):
    from warehouse_tools.engine_core.io_utils import to_num

    text = f"{whole:,}".replace(",", " ") + f",{decimals:02d}"
    expected = float(f"{whole}.{decimals:02d}") if whole >= 0 else -float(f"{abs(whole)}.{decimals:02d}")
    assert to_num(text) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# find_col: case-insensitiv exakt träff returnerar alltid det VERKLIGA
# kolumnnamnet; miss utan default ger KeyError; miss med required=False ger
# default. Skyddar fuzzy-matchningen som hela CSV-inläsningen vilar på.
# ---------------------------------------------------------------------------


_col_name = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), max_codepoint=0x017F),
    min_size=3,
    max_size=12,
)


@given(st.lists(_col_name, min_size=1, max_size=6, unique_by=lambda s: s.lower()), st.data())
@settings(max_examples=100, deadline=None)
def test_find_col_exact_match_is_case_insensitive(columns, data):
    from warehouse_tools.engine_core.io_utils import find_col

    frame = pd.DataFrame(columns=columns)
    target = data.draw(st.sampled_from(columns))
    mangled = data.draw(st.sampled_from([target.lower(), target.upper(), target]))
    # Kontraktet är lower()-ekvivalens; tecken som ß (upper() -> SS) faller
    # utanför — Hypothesis hittade det själv. Dokumenterat med assume.
    assume(mangled.lower() == target.lower())
    assert find_col(frame, [mangled]) == target


@given(st.lists(_col_name, min_size=1, max_size=4, unique_by=lambda s: s.lower()))
@settings(max_examples=50, deadline=None)
def test_find_col_miss_raises_or_returns_default(columns):
    from warehouse_tools.engine_core.io_utils import find_col

    frame = pd.DataFrame(columns=columns)
    # "\x00" kan aldrig vara del av ett kolumnnamn ur våra strategier.
    with pytest.raises(KeyError):
        find_col(frame, ["\x00finns-inte\x00"])
    assert find_col(frame, ["\x00finns-inte\x00"], required=False, default="fallback") == "fallback"


# ---------------------------------------------------------------------------
# smart_to_datetime: ISO-datum och kompakta ÅÅÅÅMMDD-datum ska båda tolkas
# till exakt samma datum utan NaT — oavsett blandning av dagar/månader som
# annars lurar dayfirst-heuristiker.
# ---------------------------------------------------------------------------


@given(st.lists(st.dates(min_value=pd.Timestamp("2000-01-01").date(), max_value=pd.Timestamp("2035-12-31").date()), min_size=1, max_size=40))
@settings(max_examples=100, deadline=None)
def test_smart_to_datetime_roundtrips_iso_and_compact(dates):
    from warehouse_tools.engine_core.io_utils import smart_to_datetime

    iso = smart_to_datetime(pd.Series([d.isoformat() for d in dates]))
    compact = smart_to_datetime(pd.Series([d.strftime("%Y%m%d") for d in dates]))
    assert list(iso.dt.date) == dates
    assert list(compact.dt.date) == dates
