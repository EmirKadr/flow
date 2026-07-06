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
from hypothesis import given, settings, strategies as st

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
