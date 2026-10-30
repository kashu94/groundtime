from datetime import UTC, date, datetime

import pytest

from crewops.domain import (
    AircraftType,
    Crew,
    CrewStatus,
    DataError,
    Flight,
    Pairing,
    Rank,
    parse_utc,
)

CREW = {
    "crew_id": "C-1042",
    "name": "A. Nair",
    "rank": "Captain",
    "base": "BLR",
    "ratings": ["A320"],
    "seniority": 22,
    "reachability_minutes": 90,
    "status": "active",
}

FLIGHT = {
    "flight_id": "DX401-2026-10-12",
    "flight_no": "DX401",
    "date": "2026-10-12",
    "dep_station": "BLR",
    "arr_station": "DEL",
    "dep_utc": "2026-10-12T02:30:00Z",
    "arr_utc": "2026-10-12T05:15:00Z",
    "block_hours": 2.75,
    "aircraft": "VT-DXA",
    "aircraft_type": "A320",
    "seats": 162,
}


def test_crew_parses_into_typed_fields():
    c = Crew.from_dict(CREW)
    assert c.rank is Rank.CAPTAIN
    assert c.rank.is_pilot
    assert c.ratings == (AircraftType.A320,)
    assert c.status is CrewStatus.ACTIVE


def test_unknown_enum_names_the_field():
    with pytest.raises(DataError, match=r"crew\.rank: unknown value 'Pilot'"):
        Crew.from_dict({**CREW, "rank": "Pilot"})


def test_missing_field_names_the_field():
    bad = {k: v for k, v in CREW.items() if k != "base"}
    with pytest.raises(DataError, match=r"crew\.base: missing"):
        Crew.from_dict(bad)


def test_bad_station_code_is_rejected():
    with pytest.raises(DataError, match="station code"):
        Crew.from_dict({**CREW, "base": "Bangalore"})


def test_boolean_is_not_an_integer():
    with pytest.raises(DataError, match="seniority"):
        Crew.from_dict({**CREW, "seniority": True})


def test_timestamps_are_aware_utc():
    f = Flight.from_dict(FLIGHT)
    assert f.dep_utc == datetime(2026, 10, 12, 2, 30, tzinfo=UTC)
    assert f.dep_utc.tzinfo is not None


def test_naive_timestamp_is_rejected():
    with pytest.raises(DataError, match="no timezone"):
        parse_utc("2026-10-12T02:30:00")


def test_flight_must_land_after_departure():
    with pytest.raises(DataError, match="not after departure"):
        Flight.from_dict({**FLIGHT, "arr_utc": "2026-10-12T02:00:00Z"})


def test_pairing_days_sorted_and_helpers():
    p = Pairing.from_dict(
        {
            "pairing_id": "P-1",
            "aircraft": "VT-DXA",
            "days": [
                {
                    "date": "2026-10-13",
                    "flights": ["B"],
                    "report_utc": "2026-10-13T01:00:00Z",
                    "release_utc": "2026-10-13T09:00:00Z",
                },
                {
                    "date": "2026-10-12",
                    "flights": ["A"],
                    "report_utc": "2026-10-12T01:00:00Z",
                    "release_utc": "2026-10-12T09:00:00Z",
                },
            ],
            "crew": [
                {"crew_id": "C-1", "role": "Captain"},
                {"crew_id": "C-2", "role": "Cabin Crew"},
            ],
        }
    )
    assert p.first_day.date == date(2026, 10, 12)
    assert p.flight_ids == ("A", "B")
    assert p.holder(Rank.CAPTAIN) == ("C-1",)
    assert p.holder(Rank.FIRST_OFFICER) == ()


def test_pairing_needs_days():
    with pytest.raises(DataError, match="at least one day"):
        Pairing.from_dict({"pairing_id": "P-1", "aircraft": "X", "days": [], "crew": []})
