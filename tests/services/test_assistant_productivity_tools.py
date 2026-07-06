"""Tester för apphjälpens nya produktivitets-tools (nattpass 2026-07-06).

Täcker: productivity_trend, productivity_person_compare,
productivity_process_trend, productivity_anomalies.
Alla förväntansvärden är handräknade ur seed-datat nedan.
"""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend import assistant_tools
from app.backend.database import Base
from app.backend.models import Business, Person, PersonProductivityDaily, User


def make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def prod_row(business_id, person_id, day, points, minutes, process_key, process_label):
    return PersonProductivityDaily(
        business_id=business_id,
        snapshot_date=day,
        person_id=person_id,
        row_type="activity",
        item_key=f"{process_key}-{day.isoformat()}",
        metric="points",
        process_key=process_key,
        process_label=process_label,
        kpi_points=points,
        kpi_minutes=minutes,
        units=points,
    )


def seed(session):
    stigamo = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    r3 = Business(code="R3", name="R3", sort_order=2)
    session.add_all([stigamo, r3])
    session.flush()
    anna = Person(business_id=stigamo.id, name="Anna Andersson")
    bert = Person(business_id=stigamo.id, name="Bert Berg")
    rut = Person(business_id=r3.id, name="Rut R3")
    session.add_all([anna, bert, rut])
    session.flush()
    leader = User(username="ledare", role="leader", roles=["leader"], business_id=stigamo.id, is_active=True)
    session.add(leader)
    session.flush()

    # Vecka 23 (2026-06-01 är måndag): Anna 10 p/dag mån-fre + 200 p lördag.
    for day_number in range(1, 6):
        session.add(prod_row(stigamo.id, anna.id, date(2026, 6, day_number), 10.0, 60, "plock", "Plock"))
    session.add(prod_row(stigamo.id, anna.id, date(2026, 6, 6), 200.0, 60, "plock", "Plock"))
    # Bert: 50 p tisdag vecka 23 och 20 p måndag vecka 24, process mottag.
    session.add(prod_row(stigamo.id, bert.id, date(2026, 6, 2), 50.0, 120, "mottag", "Mottag"))
    session.add(prod_row(stigamo.id, bert.id, date(2026, 6, 8), 20.0, 60, "mottag", "Mottag"))
    # R3-data som aldrig får synas för Stigamo-ledaren.
    session.add(prod_row(r3.id, rut.id, date(2026, 6, 3), 999.0, 60, "plock", "Plock"))
    session.commit()
    return {"stigamo": stigamo, "leader": leader, "anna": anna, "bert": bert}


def run(session, user, name, args):
    payload = assistant_tools.run_tool(session, user, name, args)
    assert "error" not in payload, payload
    return payload["result"]


def test_productivity_trend_buckets_iso_weeks_and_scopes():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(
            session, data["leader"], "productivity_trend",
            {"date_from": "2026-06-01", "date_to": "2026-06-14"},
        )
        assert [week["week"] for week in result["weeks"]] == ["2026-V23", "2026-V24"]
        v23, v24 = result["weeks"]
        # V23: Anna 5*10+200=250 + Bert 50 = 300 poäng, 2 personer. Ruts 999 (R3) exkluderas.
        assert v23 == {"week": "2026-V23", "kpi_points": 300.0, "kpi_minutes": 480, "persons": 2}
        assert v24 == {"week": "2026-V24", "kpi_points": 20.0, "kpi_minutes": 60, "persons": 1}
    finally:
        session.close()
        engine.dispose()


def test_productivity_person_compare_rank_and_average():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(
            session, data["leader"], "productivity_person_compare",
            {"person": "Anna Andersson", "date_from": "2026-06-01", "date_to": "2026-06-07"},
        )
        # Anna 250 p, Bert 50 p -> snitt 150, diff +100, rank 1 av 2.
        assert result["kpi_points"] == 250.0
        assert result["average_kpi_points"] == 150.0
        assert result["diff_vs_average"] == 100.0
        assert result["rank"] == 1
        assert result["persons_with_data"] == 2
        assert result["points_per_hour"] == 41.7  # 250 p / 6 h

        empty = run(
            session, data["leader"], "productivity_person_compare",
            {"person": "Anna Andersson", "date_from": "2025-01-01", "date_to": "2025-01-07"},
        )
        assert "note" in empty
    finally:
        session.close()
        engine.dispose()


def test_productivity_process_trend_matches_and_rejects():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(
            session, data["leader"], "productivity_process_trend",
            {"process": "plock", "date_from": "2026-06-01", "date_to": "2026-06-07"},
        )
        assert result["process_key"] == "plock"
        assert len(result["days"]) == 6
        assert result["days"][-1]["kpi_points"] == 200.0

        unknown = assistant_tools.run_tool(
            session, data["leader"], "productivity_process_trend",
            {"process": "xyz", "date_from": "2026-06-01", "date_to": "2026-06-07"},
        )
        assert "Ingen process matchade" in unknown["error"]
        assert "plock" in unknown["error"]  # felet listar tillgängliga processer
    finally:
        session.close()
        engine.dispose()


def test_productivity_anomalies_flags_the_outlier_day():
    engine, session = make_session()
    data = seed(session)
    try:
        result = run(
            session, data["leader"], "productivity_anomalies",
            {"date_from": "2026-06-01", "date_to": "2026-06-06"},
        )
        # Dagstotaler: 10, 60, 10, 10, 10, 200 -> mean 50, std ~69.5, z(200) ~2.16.
        assert result["mean_kpi_points"] == 50.0
        assert result["days_with_data"] == 6
        assert len(result["anomalies"]) == 1
        outlier = result["anomalies"][0]
        assert outlier["date"] == "2026-06-06"
        assert outlier["z_score"] > 2
        assert outlier["weekday"] == "lördag"

        sparse = run(
            session, data["leader"], "productivity_anomalies",
            {"date_from": "2026-06-08", "date_to": "2026-06-09"},
        )
        assert sparse["anomalies"] == []
        assert "minst 3" in sparse["note"]
    finally:
        session.close()
        engine.dispose()
