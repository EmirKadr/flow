"""Property-baserade tester (Hypothesis) för engine_core:s rena funktioner.

Golden-testerna låser beteendet för FASTA indata; de här attackerar med
genererade. Egenskaper i stället för exempel: "utdata innehåller aldrig
'nan'", "summan av chunks == indata", "web och desktop delar identiskt".
Pandas 3-buggen (NaN -> "nan" i Plockplats) hade fångats här.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import assume, given, settings, strategies as st

from warehouse_tools.engine_core.allocation import _saldo_maps, calculate_refill
from warehouse_tools.engine_core.io_utils import normalize_saldo, smart_to_datetime
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
    iso = smart_to_datetime(pd.Series([d.isoformat() for d in dates]))
    compact = smart_to_datetime(pd.Series([d.strftime("%Y%m%d") for d in dates]))
    assert list(iso.dt.date) == dates
    assert list(compact.dt.date) == dates


# ---------------------------------------------------------------------------
# calculate_refill: FIFO-ordningen och Plockplats-kontraktet.
#
# calculate_refill:s refill-tabeller skyddas i dag bara av golden-snapshotsen
# (tests/services/golden*/warehouse_flows/allocate.json). De testerna kraver
# testdata som inte alltid finns, och en sha256 sager inte VILKEN invariant
# som brast. De tva testerna nedan laser de tva invarianter som en
# optimering av funktionen lattast rakar bryta.
# ---------------------------------------------------------------------------

def _fifo_buffer_interleaved() -> pd.DataFrame:
    """Buffert for EN artikel: 200 pallar med identisk tidsstampel, 100 utan
    datum (NaT) och 100 med senare tidsstampel - INTERFOLIERADE i radordningen.

    Interfolieringen ar hela poangen. En tidigare version av den har fixturen
    lade datumen i BLOCK (200 x d1, sedan 100 x NaT, sedan 100 x d2). Det gjorde
    testet vakuost: `na_position="last"` lyfter ut NaT-raderna ur argsort:en, sa
    nyckelarrayen som sorteringen faktiskt ser blir [d1 x200, d2 x100] - REDAN
    SORTERAD. En global stabil forsortering permuterar da ingenting, mutationen
    blir en no-op och testet forblir gront aven nar invarianten ar bruten.

    Med shufflade datum ar per-artikel-nyckelordningen OSORTERAD, och quicksort:ens
    tie-permutation skiljer sig darmed mellan "originalordning" och "globalt
    forsorterad" - vilket ar precis det testet ska kunna se.
    """
    rng = np.random.default_rng(20260714)
    n = 400
    dates = np.array(["2026-01-01"] * 200 + [""] * 100 + ["2026-01-02"] * 100)
    rng.shuffle(dates)
    return pd.DataFrame(
        {
            "Artikelnr": ["A"] * n,
            "Antal": rng.integers(1, 50, n).astype(float),
            "Inlagringsdatum": dates.tolist(),
            "Pallid": [f"P{i}" for i in range(n)],
            "Status": ["29"] * n,
        }
    )


@pytest.mark.parametrize("pallets_needed", [3, 7, 13, 20, 37, 120, 250, 350])
def test_refill_fifo_order_is_per_group_default_sort_on_original_row_order(pallets_needed):
    """FIFO-ordningen per artikel MASTE vara pandas per-grupp `sort_values`
    (default quicksort, na_position="last") pa raderna i URSPRUNGLIG radordning.

    Kolumnen "FIFO-baserad beräkning" ar antalet pallar som behovet ater upp i
    FIFO-ordning - alltsa en direkt funktion av tie-brytningen. Bufferten har 200
    pallar med identisk tidsstampel, sa en GLOBAL stabil forsortering (mergesort)
    av bufferten fore grupperingen ger en ANNAN ordning och darmed ett annat antal.

    Testet laser BADA halvorna av invarianten:
      - "per-grupp default sort": expected_qty jamfors mot motorns utdata.
      - "on original row order": sjalvkontrollen nedan bevisar att en global
        forsortering faktiskt ANDRAR ordningen pa just den har datan. Utan den
        kontrollen kunde fixturen tyst bli icke-diskriminerande igen (se
        _fifo_buffer_interleaved) och testet forvandlas till guardrail-teater.
    """
    buffer_raw = _fifo_buffer_interleaved()

    # Referensordning: exakt det motorn ska gora - parsa med samma parser och
    # sortera med pandas default pa raderna i indataordning.
    ref = buffer_raw.copy()
    ref["_received"] = smart_to_datetime(ref["Inlagringsdatum"])
    expected_qty = ref.sort_values("_received")["Antal"].tolist()

    # SJALVKONTROLL: datan maste diskriminera mot den forbjudna varianten.
    # Detta ar mutationen som fixens kodkommentar varnar for - global stabil
    # forsortering fore grupperingen, sedan per-grupp-sort som vanligt.
    mutant_qty = (
        ref.sort_values("_received", kind="mergesort")
        .sort_values("_received")["Antal"]
        .tolist()
    )
    assert mutant_qty != expected_qty, (
        "Fixturen diskriminerar inte langre mellan per-grupp-sort pa "
        "originalordning och global forsortering - guardrailen ar tandlos."
    )

    # Behovet ar exakt summan av de N forsta pallarna i FIFO-ordning, sa
    # "FIFO-baserad beräkning" maste bli exakt N.
    behov = float(sum(expected_qty[:pallets_needed]))
    allocated = pd.DataFrame(
        {"Artikel": ["A"], "Antal": [behov], "Källtyp": ["HUVUDPLOCK"], "Källa": [""]}
    )

    refill_hp, _refill_as = calculate_refill(allocated, buffer_raw)

    assert len(refill_hp) == 1
    row = refill_hp.iloc[0]
    assert int(row["Behov (kolli)"]) == int(behov)
    assert int(row["FIFO-baserad beräkning"]) == pallets_needed


def test_refill_excludes_helpall_pallets_already_allocated():
    """`calculate_refill`:s docstring lovar: "HELPALL-pallar som redan anvands
    exkluderas alltid". Det har testet ar den utfastelsens enda tackning.

    Tidigare guardrails skickade alltid Kalla=[""], sa `used_help_ids` var alltid
    TOM - exkluderingen kunde tas bort helt utan att nagot test rodnade. Har ar
    den ickeom: pall P1 (100 kolli, aldst) ar redan uppaten av en HELPALL-rad och
    far darfor INTE rakans som tillgangligt buffertsaldo. Refillbehovet (20) maste
    tackas av P2-P5 (5 kolli styck) = 4 pallar. Utan exkluderingen skulle P1 ligga
    forst i FIFO-kon och svara for hela behovet -> 1 pall.
    """
    buffer_raw = pd.DataFrame(
        {
            "Artikelnr": ["A"] * 5,
            "Antal": [100.0, 5.0, 5.0, 5.0, 5.0],
            "Inlagringsdatum": [
                "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05",
            ],
            "Pallid": ["P1", "P2", "P3", "P4", "P5"],
            "Status": ["29"] * 5,
        }
    )
    allocated = pd.DataFrame(
        {
            "Artikel": ["A", "A"],
            "Antal": [100.0, 20.0],
            "Källtyp": ["HELPALL", "HUVUDPLOCK"],
            "Källa": ["P1", ""],          # <- ICKE-TOM: used_help_ids == {"P1"}
        }
    )

    refill_hp, _refill_as = calculate_refill(allocated, buffer_raw)

    assert len(refill_hp) == 1
    row = refill_hp.iloc[0]
    assert int(row["Behov (kolli)"]) == 20
    # 4 = P2..P5. Utan exkluderingen av P1 blir det 1.
    assert int(row["FIFO-baserad beräkning"]) == 4
    # Tillgangligt saldo = 20 (P2..P5), inte 120. Exakt jamnt -> "Ja".
    assert row["Tillräckligt tillgängligt saldo i buffert"] == "Ja"


def test_refill_autostore_key_order_is_sorted_and_breaks_output_ties():
    """Fixens egen kodkommentar markerar detta "KRITISKT": `behov_per_art_as`
    MASTE behalla sort=True (default).

    Dikten ITERERAS for att bygga rows_as, och rows_as sorteras sedan
    ICKE-STABILT pa "FIFO-baserad beräkning". Nar flera artiklar har SAMMA
    FIFO-varde avgors deras inbordes ordning i utdatatabellen darfor helt av
    nyckelordningen. sort=False (forsta-forekomst-ordning) ger en annan
    utdataordning an sort=True (sorterad ordning).

    Datan har ar konstruerad sa att forsta-forekomst-ordningen (D, C, B, A) ar
    den OMVANDA av den sorterade (A, B, C, D), och alla fyra artiklar hamnar pa
    samma FIFO-varde. Ingen av de ovriga guardrails nar autostore-grenen alls.
    """
    buffer_raw = pd.DataFrame(
        {
            "Artikelnr": ["D", "C", "B", "A"],
            "Antal": [50.0, 50.0, 50.0, 50.0],
            "Inlagringsdatum": ["2026-01-01"] * 4,
            "Pallid": ["P1", "P2", "P3", "P4"],
            "Status": ["29"] * 4,
        }
    )
    allocated = pd.DataFrame(
        {
            "Artikel": ["D", "C", "B", "A"],   # forsta-forekomst != sorterad
            "Antal": [10.0, 10.0, 10.0, 10.0],
            "Källtyp": ["AUTOSTORE"] * 4,
            "Källa": ["", "", "", ""],         # blank Kalla -> refillbehov
        }
    )

    _refill_hp, refill_as = calculate_refill(allocated, buffer_raw)

    assert len(refill_as) == 4
    # SJALVKONTROLL: tie-brytningen ar bara meningsfull om alla FIFO-varden ar
    # LIKA. Skulle de sara pa sig skulle sorteringen avgora ordningen sjalv och
    # testet sluta se nyckelordningen.
    assert set(refill_as["FIFO-baserad beräkning"]) == {1}
    # Med sort=True byggs rows_as i SORTERAD nyckelordning (A, B, C, D), och
    # desc-sorteringen pa ett helt tie:at falt lamnar den ordningen orord.
    # Med sort=False vore nyckelordningen forsta-forekomst (D, C, B, A) och
    # utdatan blev D, C, B, A.
    assert list(refill_as["Artikel"]) == ["A", "B", "C", "D"]


# ---------------------------------------------------------------------------
# Flyttalssemantik: summeringen per grupp MASTE ga via numpy pairwise
# (per-grupp `Series.sum()`), inte via pandas cythoniserade, KAHAN-KOMPENSERADE
# `group_sum`. De tva vagarna kan skilja i sista ULP:en, och `calculate_refill`
# gor `round()`/`int()` pa summorna - en ULP blir da +/-1 pall i utdatan.
#
# Kanariedatan nedan ar konstruerad sa att exakt det intraffar. Varje test gor
# ocksa en SJALVKONTROLL att de tva summeringsvagarna fortfarande divergerar pa
# datan; slutar de gora det (t.ex. efter en numpy-/pandas-uppgradering) failar
# testet HOGT i stallet for att tyst bli tandlost.
# ---------------------------------------------------------------------------

# 23 kvantiteter vars exakta summa ligger precis pa en halv-heltalsgrans.
# pairwise -> 11259.5            -> round() -> 11260
# Kahan    -> 11259.499999999998 -> round() -> 11259
_ULP_CANARY_QTY = [
    950.4636963259353, 144.15961271963374, 948.6494471372439, 311.83145201048546,
    423.32644897257563, 827.7025938204417, 409.1991363691613, 549.5936876730595,
    27.559113243068367, 753.5131086748066, 538.1433132192782, 329.73171649909216,
    788.4287034284043, 303.19482929164496, 453.4978894806515, 134.04169724716473,
    403.11298644712923, 203.45524067614963, 262.3133404418495, 750.3646726300526,
    280.4087579860399, 485.1909744316351, 981.617581274495,
]


def _pairwise_vs_compensated() -> tuple[float, float]:
    """(pairwise-summa, Kahan-kompenserad summa) for kanariedatan."""
    values = pd.Series(_ULP_CANARY_QTY, dtype=float)
    keys = pd.Series(["A"] * len(_ULP_CANARY_QTY))
    pairwise = float(values.groupby(keys).apply(lambda s: float(s.sum())).iloc[0])
    compensated = float(values.groupby(keys).sum().iloc[0])
    return pairwise, compensated


def _assert_canary_still_discriminates(pairwise: float, compensated: float) -> None:
    assert pairwise != compensated, (
        "Kanariedatan skiljer inte langre pa pairwise och kompenserad summering "
        f"({pairwise.hex()}) - guardrailen ar tandlos och maste konstrueras om."
    )
    assert round(pairwise) != round(compensated), (
        "Kanariedatan divergerar men inte over en round()-grans - guardrailen "
        "skyddar da inte langre utdatakolumnen."
    )


def test_refill_npu_sum_uses_pairwise_series_sum_not_compensated_group_sum():
    """"Ej inlagrade (antal)" = int(round(npu_sum)). Summeringsvagen for npu_sum
    maste darfor vara den numpy-pairwise som fanns fore optimeringen.

    Byter man till `npu_qty.groupby(key).sum()` (pandas Kahan-kompenserade
    group_sum) flyttar sig kolumnen med 1 pa den har datan.
    """
    pairwise, compensated = _pairwise_vs_compensated()
    _assert_canary_still_discriminates(pairwise, compensated)

    buffer_raw = pd.DataFrame(
        {
            "Artikelnr": ["A"],
            "Antal": [10.0],
            "Inlagringsdatum": ["2026-01-01"],
            "Pallid": ["P1"],
            "Status": ["29"],
        }
    )
    allocated = pd.DataFrame(
        {"Artikel": ["A"], "Antal": [5.0], "Källtyp": ["HUVUDPLOCK"], "Källa": [""]}
    )
    not_putaway = pd.DataFrame(
        {
            "Artikel": ["A"] * len(_ULP_CANARY_QTY),
            "Antal": _ULP_CANARY_QTY,
        }
    )

    refill_hp, _refill_as = calculate_refill(
        allocated, buffer_raw, not_putaway_df=not_putaway
    )

    assert len(refill_hp) == 1
    assert int(refill_hp.iloc[0]["Ej inlagrade (antal)"]) == round(pairwise)


def test_refill_autostore_behov_uses_pairwise_series_sum_not_compensated_group_sum():
    """Samma flyttalskontrakt for autostore-grenens `behov_per_art_as`:
    "Behov (kolli)" = int(max(0, round(behov) - saldo)), sa en ULP i summan blir
    +/-1 kolli i refill-tabellen.
    """
    pairwise, compensated = _pairwise_vs_compensated()
    _assert_canary_still_discriminates(pairwise, compensated)

    buffer_raw = pd.DataFrame(
        {
            "Artikelnr": ["A"],
            "Antal": [10.0],
            "Inlagringsdatum": ["2026-01-01"],
            "Pallid": ["P1"],
            "Status": ["29"],
        }
    )
    allocated = pd.DataFrame(
        {
            "Artikel": ["A"] * len(_ULP_CANARY_QTY),
            "Antal": _ULP_CANARY_QTY,
            "Källtyp": ["AUTOSTORE"] * len(_ULP_CANARY_QTY),
            "Källa": [""] * len(_ULP_CANARY_QTY),
        }
    )

    _refill_hp, refill_as = calculate_refill(allocated, buffer_raw)

    assert len(refill_as) == 1
    assert int(refill_as.iloc[0]["Behov (kolli)"]) == round(pairwise)


# ---------------------------------------------------------------------------
# _saldo_maps: Plockplats-kontraktet.
#
# OBS varfor testet gar direkt mot _saldo_maps: i PRODUKTION matas _saldo_maps
# med saldo som ANROPAREN redan normaliserat (allocation_flows._read_
# normalized_saldo -> normalize_saldo), som REDAN kollapsat till en rad per
# artikel med forsta icke-tomma plockplatsen och fillna:at bort NaN. Via den
# produktionsvagen ar maskningen och NaN-vakten oatkomliga - ett test den vagen
# passerar aven om de vore borttagna. Darfor testas de direkt mot _saldo_maps
# har. (calculate_refill sjalv kor inte langre nagon inre normalize_saldo -
# efter W1 kan flerradig, icke-normaliserad saldo na _saldo_maps via
# calculate_refill, vilket test_refill_plockplats_end_to_end_contract nedan
# faktiskt utnyttjar.) Invarianten ar defense-in-depth for just den vagen.
# ---------------------------------------------------------------------------


def test_saldo_maps_plockplats_is_first_non_empty_in_row_order():
    """Plockplats = FORSTA ICKE-TOMMA i radordning, inte forsta raden.

    Artikel A har tom plockplats pa forsta raden och "A-02" pa andra. Ett
    `groupby().first()` pa HELA kolumnen (i stallet for pa den maskade,
    icke-tomma delen) ger "" har - det ar buggen testet later rodna.
    """
    s_norm = pd.DataFrame(
        {
            "Artikel": ["A", "A", "B"],
            "Plocksaldo": [1.0, 2.0, 3.0],
            "Plockplats": ["", "A-02", "B-01"],
        }
    )

    _saldo_sum, plockplats = _saldo_maps(s_norm)

    assert plockplats["A"] == "A-02"
    assert plockplats["B"] == "B-01"


def test_saldo_maps_never_leaks_the_string_nan():
    """NaN ar truthy: utan `where(notna(), "")`-vakten blir en tom plockplats
    strangen "nan" i refill-tabellerna (pandas laser tomma celler som NaN).

    Artikel B har bara NaN/tomt och maste sakna post i dikten (uppslag -> "").
    """
    s_norm = pd.DataFrame(
        {
            "Artikel": ["A", "B", "B"],
            "Plocksaldo": [1.0, 2.0, 3.0],
            "Plockplats": ["A-01", float("nan"), ""],
        }
    )

    _saldo_sum, plockplats = _saldo_maps(s_norm)

    assert plockplats["A"] == "A-01"
    assert plockplats.get("B", "") == ""
    assert not any(str(v).strip().lower() == "nan" for v in plockplats.values())


def test_saldo_maps_sums_plocksaldo_per_article():
    """Plocksaldo summeras per artikel (och nycklarna ar trimmade strangar)."""
    s_norm = pd.DataFrame(
        {
            "Artikel": ["A", "B", "A"],
            "Plocksaldo": [1.5, 2.0, 2.5],
            "Plockplats": ["A-01", "B-01", "A-02"],
        }
    )

    saldo_sum, _plockplats = _saldo_maps(s_norm)

    assert saldo_sum == {"A": pytest.approx(4.0), "B": pytest.approx(2.0)}


def test_refill_plockplats_end_to_end_contract():
    """End-to-end: Plockplats i refill-tabellen kommer fran saldofilen via
    _saldo_maps, och strangen "nan" lacker aldrig ut.

    Detta ar ett INTEGRATIONSTEST for ledningsdragningen. Efter W1 kor
    calculate_refill ingen inre normalize_saldo langre, sa den FLERRADIGA,
    icke-normaliserade saldon nedan nar _saldo_maps direkt via calculate_refill
    - dvs harifran TRIGGAS maskningen och NaN-vakten faktiskt. Assertionerna ar
    ovandrade och passerar bade fore och efter W1 (produktionsvagen matar
    daremot alltid redan normaliserad, en-rad-per-artikel saldo).
    """
    buffer_raw = pd.DataFrame(
        {
            "Artikelnr": ["A", "B"],
            "Antal": [10.0, 10.0],
            "Inlagringsdatum": ["2026-01-01", "2026-01-01"],
            "Pallid": ["P1", "P2"],
            "Status": ["29", "29"],
        }
    )
    allocated = pd.DataFrame(
        {
            "Artikel": ["A", "B"],
            "Antal": [5.0, 5.0],
            "Källtyp": ["HUVUDPLOCK", "HUVUDPLOCK"],
            "Källa": ["", ""],
        }
    )
    saldo = pd.DataFrame(
        {
            "Artikel": ["A", "A", "B", "B"],
            "Plocksaldo": [0.0, 0.0, 0.0, 0.0],
            "Plockplats": ["", "A-02", float("nan"), ""],
        }
    )

    refill_hp, _refill_as = calculate_refill(allocated, buffer_raw, saldo_df=saldo)

    by_art = dict(zip(refill_hp["Artikel"], refill_hp["Plockplats"]))
    assert by_art["A"] == "A-02"
    assert by_art["B"] == ""
    assert "nan" not in set(refill_hp["Plockplats"].astype(str))


# ---------------------------------------------------------------------------
# W1-GUARDRAILS: den inre normalize_saldo togs bort ur calculate_refill.
#
# Den enda produktionsanroparen (allocation_flows._read_normalized_saldo)
# skickar REDAN normaliserad saldo (en rad per artikel). Den inre
# normalize_saldo(saldo_df) var darfor en no-op och togs bort. Borttaget ar
# beteendebevarande PRECIS SA LANGE tva invarianter haller:
#   (G1a) normalize_saldo ar idempotent pa redan normaliserad saldo, sa att
#         _saldo_maps(normalize_saldo(x)) == _saldo_maps(x) bit-exakt.
#   (G1b) calculate_refill kor faktiskt ingen inre normalize_saldo langre.
#   (G2)  ingen framtida anropare matar en ICKE-normaliserad (flerradig) saldo
#         in i calculate_refill - da skulle _saldo_maps Kahan-groupby.sum gora
#         den verkliga flerradskollapsen och kunna flippa en refill-pall +/-1
#         ULP utan att nagon golden marker det.
# ---------------------------------------------------------------------------


def test_saldo_maps_normalize_saldo_is_idempotent_guardrail():
    """G1a: normalize_saldo ar idempotent pa redan normaliserad saldo.

    Bygg saldo_norm ur flerradig raadata med ULP-kanari-Plocksaldon och alla
    Plockplats-varianter (tom, whitespace, float('nan'), riktig kod, samt den
    LITERALA strangen "nan"). En andra normalize_saldo far inte andra vare sig
    saldo_sum (bit-exakt) eller plockplats_by_art. Rodnar om normalize_saldo
    tappar idempotens (dtype-/avrundnings-/kolumndrift) - just den egenskap som
    gor att den borttagna inre normaliseringen var beteendebevarande.
    """
    n = len(_ULP_CANARY_QTY)
    plockplats_variants = ["", "  ", float("nan"), "nan", "A-07", "  A-07  "]
    raw_multirow = pd.DataFrame(
        {
            "Artikel": ["A"] * n + ["B", "B", "C"],
            "Plocksaldo": list(_ULP_CANARY_QTY) + [1.0, 2.0, 3.5],
            "Plockplats": [plockplats_variants[i % len(plockplats_variants)] for i in range(n)]
            + [float("nan"), "B-01", ""],
        }
    )
    saldo_norm = normalize_saldo(raw_multirow)
    assert saldo_norm["Artikel"].is_unique  # en rad per artikel efter forsta normaliseringen

    saldo_sum_once, plock_once = _saldo_maps(saldo_norm)
    saldo_sum_twice, plock_twice = _saldo_maps(normalize_saldo(saldo_norm))

    # Bit-exakt float-jamforelse (inte approx): en extra normalize_saldo far
    # inte flytta en enda ULP.
    assert saldo_sum_once.keys() == saldo_sum_twice.keys()
    for art, v in saldo_sum_once.items():
        assert v.hex() == saldo_sum_twice[art].hex(), f"ULP-drift for {art}: {v!r} != {saldo_sum_twice[art]!r}"
    assert plock_once == plock_twice
    # "nan" (float-NaN-lackage) far aldrig sla igenom; literala "nan"-koder far dock finnas.
    assert saldo_sum_once == saldo_sum_twice


def test_calculate_refill_does_not_reintroduce_inner_normalize_saldo_guardrail():
    """G1b: calculate_refill kor INGEN inre normalize_saldo pa saldo_df.

    Sond: io_utils.to_num (som bara normalize_saldo anvander, INTE _saldo_maps)
    mangar 1e16 till 1.0 - regexen fangar inte exponenten. _saldo_maps slapper
    daremot igenom 1e16 oforandrat via .astype(float).

    Med behovet 100 och saldo 1e16:
      - utan inre normalize_saldo (nuvarande): saldo_sum=1e16 -> behovet helt
        tackt -> INGEN refill-rad.
      - med aterinford inre normalize_saldo: saldo_sum=to_num(1e16)=1.0 ->
        behov 99 kvar -> EN refill-rad byggs.
    Antalet rader skiljer, sa testet RODNAR om dubbelnormaliseringen ateruppstar.
    """
    from warehouse_tools.engine_core.io_utils import to_num

    # Sjalvkontroll: sonden ar bara giltig sa lange to_num faktiskt mangar vardet.
    assert to_num(1e16) == 1.0 and 1e16 != 1.0, "to_num-sonden ar tandlos - konstruera om guardrailen"

    allocated = pd.DataFrame(
        {"Artikel": ["A"], "Antal": [100.0], "Källtyp": ["HUVUDPLOCK"], "Källa": [""]}
    )
    buffer_raw = pd.DataFrame(
        {
            "Artikelnr": ["A"],
            "Antal": [500.0],
            "Inlagringsdatum": ["2026-01-01"],
            "Pallid": ["P1"],
            "Status": ["29"],
        }
    )
    saldo = pd.DataFrame({"Artikel": ["A"], "Plocksaldo": [1e16], "Plockplats": ["A-01"]})

    refill_hp, _refill_as = calculate_refill(allocated, buffer_raw, saldo_df=saldo)

    assert len(refill_hp) == 0, (
        "calculate_refill byggde en refill-rad trots att saldo (1e16) tacker behovet - "
        "tyder pa att den inre normalize_saldo(saldo_df) ater-inforts (to_num mangade 1e16 till 1.0)."
    )


def test_allocate_flow_feeds_normalized_saldo_to_calculate_refill_guardrail(tmp_path, monkeypatch):
    """G2: allocate-flodet matar EN-RAD-PER-ARTIKEL saldo in i calculate_refill.

    Spionerar pa saldo_df som verkligen nar E.calculate_refill i ett riktigt
    flow_allocate-anrop (den reella _read_normalized_saldo -> normalize_saldo
    kors), och kraver saldo_df["Artikel"].is_unique. Rodnar om en framtida
    anropare drar in en icke-normaliserad (flerradig) saldokalla, vilket skulle
    lata _saldo_maps Kahan-groupby.sum tyst gora den verkliga flerradskollapsen.
    """
    from warehouse_tools import flows
    from warehouse_tools.flows import allocation_flows

    orders_path = tmp_path / "orders.csv"
    buffer_path = tmp_path / "buffer.csv"
    saldo_path = tmp_path / "saldo.csv"
    for p in (orders_path, buffer_path, saldo_path):
        p.write_text("placeholder\n", encoding="utf-8")

    # FLERRADIG raadata per artikel: bevisar att normaliseringen faktiskt sker.
    saldo_raw = pd.DataFrame(
        {
            "Artikel": ["A", "A", "B", "B", "B"],
            "Plocksaldo": [1.0, 2.0, 3.0, 4.0, 5.0],
            "Plockplats": ["", "A-02", "B-01", "", "B-03"],
        }
    )

    def fake_read(path):
        name = Path(path).name
        if name == saldo_path.name:
            return saldo_raw.copy()
        # orders/buffer behover bara vara icke-tomma; allocate ar stubbad nedan.
        return pd.DataFrame({"Artikel": ["A"], "Antal": [1]})

    monkeypatch.setattr(allocation_flows.shared, "_read", fake_read)
    monkeypatch.setattr(
        allocation_flows.E, "allocate",
        lambda _o, _b, log=None: (pd.DataFrame({"Artikel": ["A"], "Källtyp": ["HUVUDPLOCK"]}), pd.DataFrame()),
    )
    monkeypatch.setattr(allocation_flows.E, "reclassify_skrymmande", lambda result, _s: result)
    monkeypatch.setattr(allocation_flows.E, "_merge_item_flags", lambda result, _i: result)
    monkeypatch.setattr(allocation_flows.E, "compute_pallet_spaces", lambda _r: pd.DataFrame())

    seen: dict = {}
    real_calc = allocation_flows.E.calculate_refill

    def spy_calc(result_df, buffer_raw, saldo_df=None, not_putaway_df=None):
        seen["saldo_df"] = saldo_df
        return pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(allocation_flows.E, "calculate_refill", spy_calc)

    flows.clear_allocation_cache()
    try:
        flows.FLOW_BY_ID["allocate"]["handler"](
            {"orders": orders_path, "buffer": buffer_path, "saldo": saldo_path}, {}
        )
    finally:
        flows.clear_allocation_cache()

    assert "saldo_df" in seen, "calculate_refill anropades aldrig i flow_allocate"
    saldo_df = seen["saldo_df"]
    assert isinstance(saldo_df, pd.DataFrame) and not saldo_df.empty
    assert saldo_df["Artikel"].is_unique, (
        "En ICKE-normaliserad (flerradig) saldo nadde calculate_refill - efter W1 gor "
        "calculate_refill ingen inre normalize_saldo langre, sa anroparen MASTE normalisera."
    )
    assert real_calc is calculate_refill  # sanity: vi spionerade pa den riktiga funktionen
