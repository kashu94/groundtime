"""Passengers and their trips, for Groundtime.

A traveller books flight numbers; the trip is on the first day from today on which every leg
operates and the last leg is still to leave, so the same demo bookings work on any day of the
calendar. Bookings come from ``data/team/demo_travellers.json``; in production they come from
the airline's reservation system, which this does not replace.

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
from crewops.taste.stations import IST

LOOK_AHEAD_DAYS = 8


class Position(StrEnum):
    """Where the traveller is while they wait. It decides whether they may leave."""

    AWAY = "away"
    """Not at the airport yet: at home, a hotel or in town."""
    LANDSIDE = "landside"
    """At the terminal, before security."""
    AIRSIDE = "airside"
    """Past security, or connecting without leaving: they stay in the terminal."""


@dataclass(frozen=True, slots=True)
class Traveller:
    traveller_id: str
    username: str
    name: str
    flight_nos: tuple[str, ...]
    position: Position
    taste: TasteProfile

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Traveller:
        traveller_id = str(d["traveller_id"])
        return cls(
            traveller_id=traveller_id,
            username=str(d["username"]),
            name=str(d["name"]),
            flight_nos=tuple(str(f).upper() for f in d["flights"]),
            position=Position(d.get("position") or Position.AWAY),
            taste=TasteProfile.from_dict(traveller_id, d.get("taste") or {}),
        )


def default_travellers_path() -> Path:
    return default_seed_dir().parent / "team" / "demo_travellers.json"


def load_travellers(path: Path | str | None = None) -> dict[str, Traveller]:
    """Travellers by username."""
    raw = json.loads(Path(path or default_travellers_path()).read_text(encoding="utf-8"))
    travellers = [Traveller.from_dict(t) for t in raw["travellers"]]
    return {t.username: t for t in travellers}


def trip(
    flights: Mapping[str, Flight], flight_nos: tuple[str, ...], now: datetime
) -> tuple[Flight, ...]:
    """The legs of the traveller's next trip, or () when none operates in the next days."""
    first_day: date = now.astimezone(IST).date() - timedelta(days=1)
    for offset in range(LOOK_AHEAD_DAYS + 1):
        day = first_day + timedelta(days=offset)
        legs = tuple(flights.get(f"{no}-{day.isoformat()}") for no in flight_nos)
        if all(legs) and legs[-1].dep_utc > now:  # type: ignore[union-attr]
            return legs  # type: ignore[return-value]
    return ()
