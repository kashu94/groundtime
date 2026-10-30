"""Passengers, their trips, and where they are while they wait.

A traveller books a trip in Groundtime: a direct flight, or two with a connection the same
day. The booking holds flight ids, so it names the day. The demo passengers in
``data/team/demo_travellers.json`` come already booked by flight number instead, and their
trip is on the next day every leg operates, so the demo works on any day of the calendar.

A traveller id (``TR-1001``) never leaves Groundtime: the Qloo guard refuses it like a crew id.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from crewops.domain.models import Flight
from crewops.ingestion.seed import default_seed_dir
from crewops.taste.profile import TasteProfile
from crewops.taste.stations import IST, airport_at

LOOK_AHEAD_DAYS = 8
MIN_CONNECTION = timedelta(minutes=60)
"""Shortest connection offered: deplane, walk to the next gate, board."""
MAX_CONNECTION = timedelta(hours=6)
BOOK_BEFORE = timedelta(minutes=60)
"""A flight leaving sooner than this can't be booked here."""


class Position(StrEnum):
    """Where the traveller is while they wait. It decides whether an outing is possible."""

    AWAY = "away"
    """Not at the airport yet: at home, at a hotel or in town. They can spend the delay
    nearby instead of at the terminal."""
    AIRPORT = "airport"
    """At the airport. Indian airports only let a passenger back out of the departure
    terminal with the airline's and security's clearance, so they stay in."""


@dataclass(frozen=True, slots=True)
class Traveller:
    """A demo passenger who arrives already booked."""

    traveller_id: str
    name: str
    flight_nos: tuple[str, ...]
    position: Position
    taste: TasteProfile

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Traveller:
        traveller_id = str(d["traveller_id"])
        return cls(
            traveller_id=traveller_id,
            name=str(d["name"]),
            flight_nos=tuple(str(f).upper() for f in d.get("flights") or ()),
            position=Position(d.get("position") or Position.AWAY),
            taste=TasteProfile.from_dict(traveller_id, d.get("taste") or {}),
        )


def default_travellers_path() -> Path:
    return default_seed_dir().parent / "team" / "demo_travellers.json"


def load_travellers(path: Path | str | None = None) -> dict[str, Traveller]:
    """Demo travellers by traveller id."""
    raw = json.loads(Path(path or default_travellers_path()).read_text(encoding="utf-8"))
    travellers = [Traveller.from_dict(t) for t in raw["travellers"]]
    return {t.traveller_id: t for t in travellers}


def trip(
    flights: Mapping[str, Flight], flight_nos: tuple[str, ...], now: datetime
) -> tuple[Flight, ...]:
    """The legs of a booking by flight number: the first day from yesterday on which every
    leg operates and the last is still to leave. () when none does in the next days."""
    first_day: date = now.astimezone(IST).date() - timedelta(days=1)
    for offset in range(LOOK_AHEAD_DAYS + 1):
        day = first_day + timedelta(days=offset)
        legs = tuple(flights.get(f"{no}-{day.isoformat()}") for no in flight_nos)
        if legs and all(legs) and legs[-1].dep_utc > now:  # type: ignore[union-attr]
            return legs  # type: ignore[return-value]
    return ()


@dataclass(frozen=True, slots=True)
class TripOption:
    legs: tuple[Flight, ...]

    @property
    def connection_minutes(self) -> int | None:
        if len(self.legs) < 2:
            return None
        return int((self.legs[1].dep_utc - self.legs[0].arr_utc).total_seconds() // 60)

    def to_dict(self, airline_of: Any = None) -> dict[str, Any]:
        def local(t: datetime) -> str:
            return t.astimezone(IST).strftime("%Y-%m-%d %H:%M")

        first, last = self.legs[0], self.legs[-1]
        return {
            "flight_ids": [f.flight_id for f in self.legs],
            "from": first.dep_station,
            "to": last.arr_station,
            "departs_local": local(first.dep_utc),
            "arrives_local": local(last.arr_utc),
            "via": self.legs[0].arr_station if len(self.legs) > 1 else None,
            "connection_minutes": self.connection_minutes,
            "legs": [
                {
                    "flight_id": f.flight_id,
                    "flight_no": f.flight_no,
                    "airline": airline_of(f.flight_no) if airline_of else None,
                    "from": f.dep_station,
                    "to": f.arr_station,
                    "departs_local": local(f.dep_utc),
                    "arrives_local": local(f.arr_utc),
                }
                for f in self.legs
            ],
        }


def find_trips(
    flights: Mapping[str, Flight], origin: str, destination: str, day: date, now: datetime
) -> list[TripOption]:
    """Direct flights from ``origin`` to ``destination`` leaving on ``day``, then one-stop
    trips with a same-day connection, earliest arrival first. Only flights still bookable."""
    origin, destination = origin.upper(), destination.upper()
    if origin == destination or airport_at(origin) is None or airport_at(destination) is None:
        return []
    today = [f for f in flights.values() if f.date == day]
    bookable = [f for f in today if f.dep_utc - BOOK_BEFORE > now]
    direct = [
        TripOption((f,))
        for f in bookable
        if f.dep_station == origin and f.arr_station == destination
    ]
    onward: list[TripOption] = []
    for first in bookable:
        if first.dep_station != origin or first.arr_station == destination:
            continue
        for second in today:
            if second.dep_station != first.arr_station or second.arr_station != destination:
                continue
            if MIN_CONNECTION <= second.dep_utc - first.arr_utc <= MAX_CONNECTION:
                onward.append(TripOption((first, second)))
    return sorted(direct, key=lambda t: t.legs[-1].arr_utc) + sorted(
        onward, key=lambda t: t.legs[-1].arr_utc
    )


def stations(flights: Mapping[str, Flight]) -> list[str]:
    return sorted(
        {f.dep_station for f in flights.values()} | {f.arr_station for f in flights.values()}
    )
