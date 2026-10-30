"""Loads the network's seed week from JSON and checks it hangs together.

``load_seed`` checks each record on its own (types, enums, timestamps). ``validate`` does the
cross-record checks: every pairing flies real flights on its own aircraft, legs connect, crew
fly for their own airline and are never on two trips at once.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from crewops.domain import Airline, Crew, DataError, Flight, Pairing

SEED_FILES = ("airlines.json", "crew.json", "flights.json", "rosters.json")


def default_seed_dir() -> Path:
    """``data/seed`` in the repo. The deployed MCP server bundles data next to the code and
    points ``CREWOPS_DATA_DIR`` at it."""
    if root := os.environ.get("CREWOPS_DATA_DIR"):
        return Path(root) / "seed"
    return Path(__file__).resolve().parents[3] / "data" / "seed"


@dataclass(frozen=True, slots=True)
class SeedData:
    airlines: tuple[Airline, ...]
    crew: tuple[Crew, ...]
    flights: tuple[Flight, ...]
    pairings: tuple[Pairing, ...]


def _read(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise DataError(f"{path.name}: file not found in {path.parent}") from None
    except json.JSONDecodeError as exc:
        raise DataError(f"{path.name}: invalid JSON at line {exc.lineno}: {exc.msg}") from None


def _parse_list[T](rows: Any, name: str, parse: Callable[[Any, str], T]) -> tuple[T, ...]:
    if not isinstance(rows, list):
        raise DataError(f"{name}: expected a list at the top level")
    return tuple(parse(row, f"{name}[{i}]") for i, row in enumerate(rows))


def load_seed(directory: Path | str | None = None) -> SeedData:
    """Raises ``DataError`` naming the first bad field."""
    root = Path(directory) if directory is not None else default_seed_dir()
    raw = {name: _read(root / name) for name in SEED_FILES}
    rosters = raw["rosters.json"]
    if not isinstance(rosters, dict):
        raise DataError("rosters.json must be an object at the top level")
    return SeedData(
        airlines=_parse_list(raw["airlines.json"], "airlines", Airline.from_dict),
        crew=_parse_list(raw["crew.json"], "crew", Crew.from_dict),
        flights=_parse_list(raw["flights.json"], "flights", Flight.from_dict),
        pairings=_parse_list(rosters.get("pairings"), "pairings", Pairing.from_dict),
    )


def _duplicates(ids: Iterable[str]) -> list[str]:
    return sorted(i for i, n in Counter(ids).items() if n > 1)


def validate(seed: SeedData) -> list[str]:
    """Every problem with the seed. Empty means it is safe to serve."""
    errors: list[str] = []
    for kind, ids in (
        ("airline", [a.code for a in seed.airlines]),
        ("crew", [c.crew_id for c in seed.crew]),
        ("flight", [f.flight_id for f in seed.flights]),
        ("pairing", [p.pairing_id for p in seed.pairings]),
    ):
        errors += [f"{dup}: duplicate {kind}" for dup in _duplicates(ids)]

    crew = {c.crew_id: c for c in seed.crew}
    flights = {f.flight_id: f for f in seed.flights}
    owner = {tail: a.code for a in seed.airlines for tail in a.aircraft}
    for f in seed.flights:
        if f.aircraft not in owner:
            errors.append(f"{f.flight_id}: {f.aircraft} belongs to no airline")
        elif not f.flight_no.startswith(owner[f.aircraft]):
            errors.append(f"{f.flight_id}: flies {owner[f.aircraft]}'s {f.aircraft}")

    duties: dict[str, list[tuple[datetime, datetime, str]]] = defaultdict(list)
    for p in seed.pairings:
        for day in p.days:
            legs = []
            for fid in day.flight_ids:
                if fid not in flights:
                    errors.append(f"{p.pairing_id}: {day.date}: unknown flight {fid}")
                else:
                    legs.append(flights[fid])
            for leg in legs:
                if leg.aircraft != p.aircraft:
                    errors.append(f"{p.pairing_id}: {leg.flight_id} flies {leg.aircraft}")
            for prev, nxt in zip(legs, legs[1:], strict=False):
                if prev.arr_station != nxt.dep_station or nxt.dep_utc < prev.arr_utc:
                    errors.append(f"{p.pairing_id}: {nxt.flight_id} doesn't follow on")
            for seat in p.crew:
                duties[seat.crew_id].append((day.report_utc, day.release_utc, p.pairing_id))
        for seat in p.crew:
            member = crew.get(seat.crew_id)
            if member is None:
                errors.append(f"{p.pairing_id}: unknown crew {seat.crew_id}")
            elif p.aircraft in owner and member.airline != owner[p.aircraft]:
                errors.append(f"{p.pairing_id}: {seat.crew_id} works for {member.airline}")
    for crew_id, spans in duties.items():
        spans.sort()
        for (_, end_a, pa), (start_b, _, pb) in zip(spans, spans[1:], strict=False):
            if pa != pb and start_b < end_a:
                errors.append(f"{crew_id}: double-booked, {pa} overlaps {pb}")
    return errors
