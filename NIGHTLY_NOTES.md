# Nattpass-anteckningar

Arbetslogg för OVERNIGHT_PLAN.md. Nyaste passet överst.

## Pass 2026-07-06 (branch feature/nightly-quality-20260706)

### Beslut och avvikelser

- **Ekonomi-tools, medvetet strukna ur batchen** (uppgift 1): planen föreslog
  fyra ekonomi-tools men bara `finance_summary` byggdes. Skäl:
  - `finance_process_breakdown` och `staffing_cost_summary`: pengamatten
    ligger djupt i produktivitetsrapportens cellstruktur
    (`_finance_for_productivity_cell` per tidscell). En egen aggregering vid
    sidan av skulle bli en andra sanning om pengar — mot planens regel.
    `finance_summary` återanvänder i stället hela den befintliga beräkningen
    via nya `build_business_summary_payload` (utbruten ur endpointen, delad).
  - `calc_vs_actual` (kalkyl mot faktisk bemanning): kräver förståelse av
    `StaffingCalculatorProfile`-semantiken och hur kalkylen mappar mot
    schema-celler. Osäkert underlag kl 22 — hellre stryka än gissa.
    FÖRSLAG till Emir: bygg den som deklarativ backend-funktion med egna
    tester först, sedan tool ovanpå.
- **Superuser-scope i error_trend**: super user utan verksamhetsfilter ser
  globalt (visible_business_id=None). Första testantagandet var fel; testet
  rättat, beteendet är dokumenterat och avsiktligt.

### Klart

- Uppgift 1 batch 1: 6 Historik/fel-tools + tester (commit ea58626-ish).
- Uppgift 1 batch 2: 4 produktivitets-tools + tester.
- Uppgift 1 batch 3: finance_summary + refaktor av
  /productivity/overview/business-summary till delad
  build_business_summary_payload + tester (94 produktivitets-/finanstester gröna).
- **sankey_inbound_summary struken**: load_sankey_inbound_payload är den dokumenterade OOM-vägen utan arkiv-cache; det finns ingen garanterat billig summeringsväg idag. FÖRSLAG: bygg aggregat i arkiv-cachen först.
