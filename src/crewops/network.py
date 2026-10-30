"""The airline network in memory: every flight and crew trip, from the seed week onwards.

The seed is one hand-built week (12-18 October 2026). The same flights fly at the same times
every week after it, with the same crew, up to ``LAST_DAY``, so Groundtime works on any day
of the judging window. Flight ids carry their date (``KS434-2026-10-30``); trip numbers go
up by 100 a week (P-2201, then P-2301, P-2401, ...).

Built once per process, then read-only. The network is small (about 1,700 flights) and a
plan reads it many times, so memory beats a table round trip.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from functools import cache

from crewops.domain import Crew, Flight, Pairing, PairingDay
from crewops.ingestion.seed import SeedData, load_seed

LAST_DAY = date(2026, 12, 31)
WEEK = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class Network:
    flights: Mapping[str, Flight]
    pairings: Mapping[str, Pairing]
    crew: Mapping[str, Crew]
    airline_names: Mapping[str, str]
    """Airline code -> name."""

    def airline_of(self, flight_no: str) -> str | None:
        return self.airline_names.get(flight_no[:2])


def _pairing_id(seed_id: str, week: int) -> str:
    return f"P-{int(seed_id.split('-')[1]) + 100 * week:04d}"


def build_network(seed: SeedData, last_day: date = LAST_DAY) -> Network:
    """The seed week, repeated weekly up to ``last_day``."""
    first = min(f.date for f in seed.flights)
    weeks = (last_day - first).days // 7 + 1
    flights: dict[str, Flight] = {}
    pairings: dict[str, Pairing] = {}
    for week in range(weeks):
        shift = WEEK * week
        ids: dict[str, str] = {}
        for f in seed.flights:
            on = f.date + shift
            if on > last_day:
                continue
            moved = replace(
                f,
                flight_id=f"{f.flight_no}-{on.isoformat()}",
                date=on,
                dep_utc=f.dep_utc + shift,
                arr_utc=f.arr_utc + shift,
            )
            ids[f.flight_id] = moved.flight_id
            flights[moved.flight_id] = moved
        for p in seed.pairings:
            if any(fid not in ids for fid in p.flight_ids):
                continue  # runs past the last day
            days = tuple(
                PairingDay(
                    date=d.date + shift,
                    flight_ids=tuple(ids[fid] for fid in d.flight_ids),
                    report_utc=d.report_utc + shift,
                    release_utc=d.release_utc + shift,
                )
                for d in p.days
            )
            pid = _pairing_id(p.pairing_id, week)
            pairings[pid] = replace(p, pairing_id=pid, days=days)
    return Network(
        flights=flights,
        pairings=pairings,
        crew={c.crew_id: c for c in seed.crew},
        airline_names={a.code: a.name for a in seed.airlines},
    )


@cache
def network() -> Network:
    """The network from the bundled seed, built on first use."""
    return build_network(load_seed())
