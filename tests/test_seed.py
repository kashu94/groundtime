"""The seed week loads, hangs together, and says what is wrong when it doesn't."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from crewops.domain import DataError, PairingSeat, Rank
from crewops.ingestion.seed import SEED_FILES, default_seed_dir, load_seed, validate


@pytest.fixture(scope="module")
def seed():
    return load_seed()


def test_seed_counts(seed):
    assert len(seed.crew) == 150
    assert len(seed.flights) == 147
    assert len(seed.pairings) == 39


def test_seed_has_no_errors(seed):
    assert validate(seed) == []


def test_three_airlines_each_with_its_own_aircraft_and_crew(seed):
    assert [a.code for a in seed.airlines] == ["DX", "KS", "NG"]
    owner = {tail: a.code for a in seed.airlines for tail in a.aircraft}
    assert all(f.flight_no.startswith(owner[f.aircraft]) for f in seed.flights)
    crew = {c.crew_id: c for c in seed.crew}
    for p in seed.pairings:
        assert {crew[s.crew_id].airline for s in p.crew} == {owner[p.aircraft]}, p.pairing_id


def test_crew_rostered_for_another_airline_is_an_error(seed):
    p = seed.pairings[0]  # a Deccan Express trip
    stranger = next(c for c in seed.crew if c.airline == "KS" and c.rank is Rank.CAPTAIN)
    seats = (PairingSeat(stranger.crew_id, Rank.CAPTAIN), *p.crew[1:])
    broken = replace(seed, pairings=(replace(p, crew=seats), *seed.pairings[1:]))
    assert any("works for KS" in e for e in validate(broken))


def test_double_booking_is_an_error(seed):
    a, b = (
        seed.pairings[0],
        next(p for p in seed.pairings[1:] if p.days[0].date == seed.pairings[0].days[0].date),
    )
    seats = (*b.crew[:-1], PairingSeat(a.crew[-1].crew_id, a.crew[-1].role))
    broken = replace(seed, pairings=(a, replace(b, crew=seats), *seed.pairings[2:]))
    assert any("double-booked" in e for e in validate(broken))


def test_unknown_flight_in_pairing_is_an_error(seed):
    p = seed.pairings[0]
    day = replace(p.days[0], flight_ids=("ZZ999-2026-10-12",))
    broken = replace(seed, pairings=(replace(p, days=(day, *p.days[1:])), *seed.pairings[1:]))
    assert any("unknown flight ZZ999" in e for e in validate(broken))


def test_duplicate_records_are_errors(seed):
    broken = replace(seed, flights=(*seed.flights, seed.flights[0]))
    assert any("duplicate flight" in e for e in validate(broken))


def test_missing_file_names_it(tmp_path):
    with pytest.raises(DataError, match="airlines.json: file not found"):
        load_seed(tmp_path)


def _copy(tmp_path: Path) -> Path:
    for name in SEED_FILES:
        shutil.copy(default_seed_dir() / name, tmp_path / name)
    return tmp_path


def test_bad_record_names_file_and_index(tmp_path: Path):
    root = _copy(tmp_path)
    crew = json.loads((root / "crew.json").read_text())
    crew[3]["rank"] = "Pilot"
    (root / "crew.json").write_text(json.dumps(crew))
    with pytest.raises(DataError, match=r"crew\[3\]\.rank"):
        load_seed(root)


def test_invalid_json_names_line(tmp_path: Path):
    root = _copy(tmp_path)
    (root / "flights.json").write_text("[\n{,\n")
    with pytest.raises(DataError, match="flights.json: invalid JSON at line 2"):
        load_seed(root)
