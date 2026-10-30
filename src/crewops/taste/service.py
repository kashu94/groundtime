"""Groundtime as the server offers it: bookings, delays, and the plan for each wait.

The MCP server and the concierge share this. It knows the traveller from the signed-in user
(never from what they type), takes every delay from what customer care recorded, and keeps
bookings and taste profiles in the operations table.

A booking and the taste that goes with it are saved together, when the traveller confirms
the trip, and not before: nothing they browse is kept.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from crewops.domain.models import Flight
from crewops.store import trips as trip_store
from crewops.store.taste import profile_of, save_profile
from crewops.taste.groundtime import GroundPlan, GroundWait, ground_wait, plan_groundtime
from crewops.taste.profile import DIETARY, LOVE_TYPES, TasteProfile
from crewops.taste.qloo import QlooClient, QlooError
from crewops.taste.stations import IST
from crewops.taste.travellers import (
    BOOK_BEFORE,
    MAX_CONNECTION,
    MIN_CONNECTION,
    Position,
    Traveller,
    find_trips,
    load_travellers,
    trip,
)

DELAY_CACHE_SECONDS = 5.0
MAX_DELAY_MINUTES = 12 * 60
MAX_DELAY_TIMES = 3
"""How many times customer care may mark one flight late. Clearing a delay is always allowed."""
CARE_DESK = {"name": "Groundtime customer care", "phone": "1800 000 4763", "hours": "24 hours"}
"""Shown to travellers on their trip. A placeholder number for the demo."""
SEARCH_TYPES = {k for k in LOVE_TYPES if k != "urn:tag"}
SHORTLIST: dict[str, tuple[str, ...]] = {
    "urn:entity:artist": ("A.R. Rahman", "Arijit Singh", "Shreya Ghoshal", "Coldplay"),
    "urn:entity:movie": ("Lagaan", "3 Idiots", "Zindagi Na Milegi Dobara", "RRR"),
    "urn:entity:tv_show": ("Panchayat", "Kota Factory", "The Office", "Friends"),
    "urn:entity:book": ("The God of Small Things", "The White Tiger", "Sapiens"),
}
"""What the booking screen offers at a tap, by name. Each is looked up in Qloo's catalogue,
so what is saved is Qloo's id for it; anything else is a search away."""


class GroundtimeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class Booked:
    """A traveller's trip as Groundtime plans it."""

    traveller_id: str
    name: str
    legs: tuple[Flight, ...]
    position: Position
    saved: bool
    """Booked in Groundtime; False for a demo passenger's booking from the file."""


def _iso(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def _local(at: datetime) -> str:
    return at.astimezone(IST).strftime("%Y-%m-%d %H:%M")


class Groundtime:
    def __init__(
        self,
        table: Any,
        qloo: QlooClient,
        flights: Callable[[], Mapping[str, Flight]],
        *,
        clock: Callable[[], datetime],
        travellers: Mapping[str, Traveller] | None = None,
        delays: Callable[[], Mapping[str, int]] | None = None,
    ) -> None:
        """``flights`` gives the network's flights by id; ``delays`` defaults to the delays
        recorded in ``table``. ``travellers`` are the demo passengers, by traveller id."""
        self.table = table
        self.qloo = qloo
        self.flights = flights
        self.clock = clock
        self.travellers = dict(travellers) if travellers is not None else load_travellers()
        self._delays = delays
        self._delay_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
        self._shortlist: list[dict[str, Any]] | None = None
        self._lock = threading.Lock()

    # -- Delays ----------------------------------------------------------------

    def delays(self) -> dict[str, int]:
        """Flight id -> minutes late, for flights late now."""
        if self._delays is not None:
            return dict(self._delays())
        return {
            f: int(d["delay_minutes"])
            for f, d in self._delay_records().items()
            if int(d.get("delay_minutes") or 0) > 0
        }

    def _delay_records(self) -> dict[str, dict[str, Any]]:
        """Flight id -> what customer care recorded on it (cleared ones too), cached briefly."""
        if self._delays is not None:
            return {}
        with self._lock:
            if self._delay_cache and time.monotonic() - self._delay_cache[0] < DELAY_CACHE_SECONDS:
                return self._delay_cache[1]
        found = trip_store.all_delays(self.table)
        with self._lock:
            self._delay_cache = (time.monotonic(), found)
        return found

    def _forget_delays(self) -> None:
        with self._lock:
            self._delay_cache = None

    def record_delay(self, flight_id: str, minutes: int, reason: str, by: str) -> dict[str, Any]:
        flight = self._flight(flight_id)
        if not isinstance(minutes, int) or not 0 <= minutes <= MAX_DELAY_MINUTES:
            raise GroundtimeError("INVALID", f"a delay is 0 to {MAX_DELAY_MINUTES} minutes")
        reason = (reason or "").strip()
        if len(reason) > 200:
            raise GroundtimeError("INVALID", "keep the reason under 200 characters")
        now = self.clock()
        current = trip_store.delay_of(self.table, flight_id) or {}
        late_now = int(current.get("delay_minutes") or 0)
        if flight.dep_utc + timedelta(minutes=late_now) <= now:
            raise GroundtimeError("INVALID", f"{flight.flight_no} has already left")
        if minutes and flight.dep_utc + timedelta(minutes=minutes) <= now:
            raise GroundtimeError(
                "INVALID", f"{flight.flight_no} would have left by then: give a longer delay"
            )
        if minutes == 0 and late_now == 0:
            raise GroundtimeError("INVALID", f"{flight.flight_no} isn't delayed")
        try:
            out = trip_store.record_delay(
                self.table,
                flight_id,
                minutes,
                reason or ("Not given" if minutes else "Back on time"),
                by,
                now,
                max_times=MAX_DELAY_TIMES,
            )
        except trip_store.TooManyDelays:
            raise GroundtimeError(
                "LIMIT",
                f"{flight.flight_no} has been marked late {MAX_DELAY_TIMES} times already, "
                "the most allowed",
            ) from None
        self._forget_delays()
        return (
            {"flight_id": flight_id, "delay_minutes": minutes}
            | _delay_view(out)
            | {"waiting": self._waiting_on(flight_id)}
        )

    # -- Who and when ----------------------------------------------------------

    def _flight(self, flight_id: str) -> Flight:
        flight = self.flights().get(flight_id)
        if flight is None:
            raise GroundtimeError("NOT_FOUND", f"no flight {flight_id}")
        return flight

    def booked(self, traveller_id: str) -> Booked | None:
        """Their trip: the one booked in Groundtime, else a demo passenger's from the file."""
        saved = trip_store.booking_of(self.table, traveller_id)
        flights = self.flights()
        if saved is not None:
            legs = tuple(flights[f] for f in saved["flight_ids"] if f in flights)
            if len(legs) != len(saved["flight_ids"]):
                return None
            return Booked(traveller_id, saved["name"], legs, Position(saved["position"]), True)
        demo = self.travellers.get(traveller_id)
        if demo is None or not demo.flight_nos:
            return None
        legs = trip(flights, demo.flight_nos, self.clock())
        if not legs:
            return None
        return Booked(traveller_id, demo.name, legs, demo.position, False)

    def _bookings(self) -> list[Booked]:
        """Everyone with a trip, for customer care."""
        out: dict[str, Booked] = {}
        for traveller_id in [b["traveller_id"] for b in trip_store.all_bookings(self.table)] + list(
            self.travellers
        ):
            if traveller_id not in out and (found := self.booked(traveller_id)) is not None:
                out[traveller_id] = found
        return list(out.values())

    def _waiting_on(self, flight_id: str) -> int:
        return sum(1 for b in self._bookings() if flight_id in {f.flight_id for f in b.legs})

    def taste(self, traveller_id: str) -> TasteProfile:
        """The traveller's saved taste, else the one a demo booking came with."""
        saved = profile_of(self.table, traveller_id)
        if saved is not None:
            return saved
        demo = self.travellers.get(traveller_id)
        return demo.taste if demo else TasteProfile(traveller_id)

    def wait(self, traveller_id: str) -> GroundWait:
        booked = self.booked(traveller_id)
        if booked is None:
            raise GroundtimeError("NOT_FOUND", "no trip booked yet: book one first")
        found = ground_wait(booked.legs, booked.position, self.clock(), self.delays())
        if found is None:
            raise GroundtimeError("NOT_FOUND", "every flight on this booking has left")
        return found

    def plan(self, traveller_id: str) -> GroundPlan:
        return plan_groundtime(self.wait(traveller_id), self.taste(traveller_id), self.qloo)

    # -- Booking ---------------------------------------------------------------

    def find_trips(
        self, origin: str, destination: str, day: str, airline_of: Any = None
    ) -> list[dict[str, Any]]:
        try:
            on = date.fromisoformat(day)
        except (TypeError, ValueError):
            raise GroundtimeError("INVALID", "date must be YYYY-MM-DD") from None
        found = find_trips(self.flights(), origin, destination, on, self.clock())
        return [t.to_dict(airline_of) for t in found[:12]]

    def book(
        self,
        traveller_id: str,
        username: str,
        name: str,
        flight_ids: list[str],
        position: str,
        taste: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Confirm a trip and the taste that comes with it. Everything is checked first,
        then both are saved; nothing is kept from a booking that fails."""
        if not isinstance(flight_ids, list) or not 1 <= len(flight_ids) <= 2:
            raise GroundtimeError("INVALID", "a trip is one flight, or two with a connection")
        legs = tuple(self._flight(str(f)) for f in flight_ids)
        now = self.clock()
        if legs[0].dep_utc - BOOK_BEFORE <= now:
            raise GroundtimeError("INVALID", f"{legs[0].flight_id} leaves too soon to book")
        if len(legs) == 2:
            first, second = legs
            gap = second.dep_utc - first.arr_utc
            if first.arr_station != second.dep_station or not (
                MIN_CONNECTION <= gap <= MAX_CONNECTION
            ):
                raise GroundtimeError("INVALID", "those two flights don't connect")
        try:
            where = Position(position or Position.AWAY)
        except ValueError:
            raise GroundtimeError("INVALID", "position must be away or airport") from None
        profile = TasteProfile.from_dict(traveller_id, taste)  # ProfileError if it's wrong
        booking = trip_store.save_booking(
            self.table,
            traveller_id,
            username=username,
            name=name,
            flight_ids=[f.flight_id for f in legs],
            position=where.value,
            at=now,
        )
        saved = save_profile(self.table, profile, now)
        return {"booking": booking, "taste": _without_owner(saved.to_dict())}

    def set_position(self, traveller_id: str, position: str) -> dict[str, Any]:
        try:
            where = Position(position)
        except ValueError:
            raise GroundtimeError("INVALID", "position must be away or airport") from None
        booked = self.booked(traveller_id)
        if booked is None:
            raise GroundtimeError("NOT_FOUND", "no trip booked yet: book one first")
        if booked.saved:
            trip_store.set_position(self.table, traveller_id, where.value)
        else:  # a demo booking becomes theirs, with the day it resolved to
            trip_store.save_booking(
                self.table,
                traveller_id,
                username="",
                name=booked.name,
                flight_ids=[f.flight_id for f in booked.legs],
                position=where.value,
                at=self.clock(),
            )
        return {"position": where.value}

    def shortlist(self) -> list[dict[str, Any]]:
        """Quick picks for the booking screen, as Qloo ids. Looked up once per process (and
        Qloo's answers are cached a day); a name Qloo can't find is left out."""
        if self._shortlist is not None:
            return self._shortlist
        asks = [(kind, name) for kind, names in SHORTLIST.items() for name in names]

        def one(ask: tuple[str, str]) -> dict[str, Any] | None:
            try:
                found = self.search(ask[1], ask[0], take=1)
            except (QlooError, GroundtimeError):
                return None
            return found[0] if found else None

        with ThreadPoolExecutor(max_workers=6) as pool:
            picks = [p for p in pool.map(one, asks) if p is not None]
        if picks:
            self._shortlist = picks
        return picks

    def taste_options(self) -> dict[str, Any]:
        return {
            "picks": self.shortlist(),
            "dietary": [{"id": k, "name": v} for k, v in DIETARY.items()],
            "kinds": {k: v for k, v in LOVE_TYPES.items() if k in SEARCH_TYPES},
        }

    def search(self, query: str, kind: str, take: int = 6) -> list[dict[str, Any]]:
        """Qloo's own catalogue, for picking what you love: an id, never free text."""
        query = (query or "").strip()
        if not 2 <= len(query) <= 80:
            raise GroundtimeError("INVALID", "search for 2 to 80 characters")
        if kind not in SEARCH_TYPES:
            kinds = ", ".join(sorted(SEARCH_TYPES))
            raise GroundtimeError("INVALID", f"kind must be one of {kinds}")
        body = self.qloo.search(query, kind, take=take)
        out = []
        for e in body.get("results") or ():
            if not isinstance(e, Mapping) or not e.get("entity_id"):
                continue
            props = e.get("properties") or {}
            image = (props.get("image") or {}).get("url")
            out.append(
                {
                    "id": e["entity_id"],
                    "name": e.get("name"),
                    "type": kind,
                    "year": props.get("release_year"),
                    "image": image if isinstance(image, str) else None,
                }
            )
        return out

    # -- The traveller's own view ----------------------------------------------

    def my_trip(self, traveller_id: str) -> dict[str, Any]:
        """Their booking with the latest on every leg, and the wait. No Qloo call."""
        booked = self.booked(traveller_id)
        if booked is None:
            return {"booked": False, "care": CARE_DESK}
        delays = self.delays()
        legs = [
            {
                "flight_id": f.flight_id,
                "flight_no": f.flight_no,
                "from": f.dep_station,
                "to": f.arr_station,
                "departs_local": _local(f.dep_utc),
                "arrives_local": _local(f.arr_utc),
                "delay_minutes": delays.get(f.flight_id, 0),
                "expected_departure_local": _local(
                    f.dep_utc + timedelta(minutes=delays.get(f.flight_id, 0))
                ),
            }
            for f in booked.legs
        ]
        wait = ground_wait(booked.legs, booked.position, self.clock(), delays)
        return {
            "booked": True,
            "name": booked.name,
            "position": booked.position.value,
            "legs": legs,
            "wait": wait.to_dict() if wait else None,
            # where they wait, so their own device can tell whether they are there yet
            "airport_point": ({"lat": wait.airport.lat, "lon": wait.airport.lon} if wait else None),
            "taste": _without_owner(self.taste(traveller_id).to_dict()),
            "care": CARE_DESK,
        }

    def my_plan(self, traveller_id: str) -> dict[str, Any]:
        booked = self.booked(traveller_id)
        plan = self.plan(traveller_id)
        name = booked.name if booked else ""
        return {"traveller": {"name": name}} | plan.to_dict(for_traveller=True)

    def my_taste(self, traveller_id: str) -> dict[str, Any]:
        return _without_owner(self.taste(traveller_id).to_dict())

    def save_my_taste(self, traveller_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        profile = TasteProfile.from_dict(traveller_id, body)
        saved = save_profile(self.table, profile, self.clock())
        return _without_owner(saved.to_dict())

    # -- Customer care ---------------------------------------------------------

    def flight_board(self, day: str = "") -> list[dict[str, Any]]:
        """Every departure on ``day`` (today in India if empty), with its delay and how many
        Groundtime travellers are on it."""
        now = self.clock()
        try:
            on = date.fromisoformat(day) if day else now.astimezone(IST).date()
        except ValueError:
            raise GroundtimeError("INVALID", "date must be YYYY-MM-DD") from None
        delays = self.delays()
        records = self._delay_records()
        counts = self._counts()
        rows = []
        for f in self.flights().values():
            if f.dep_utc.astimezone(IST).date() != on:
                continue
            late = delays.get(f.flight_id, 0)
            expected = f.dep_utc + timedelta(minutes=late)
            rows.append(
                {
                    "flight_id": f.flight_id,
                    "flight_no": f.flight_no,
                    "from": f.dep_station,
                    "to": f.arr_station,
                    "departs_local": _local(f.dep_utc),
                    "expected_departure_local": _local(expected),
                    "delay_minutes": late,
                    "left": expected <= now,
                    "booked": f.booked,
                    "with_app": counts.get(f.flight_id, 0),
                }
                | _delay_view(records.get(f.flight_id))
            )
        return sorted(rows, key=lambda r: r["departs_local"])

    def _counts(self) -> dict[str, int]:
        """Flight id -> Groundtime travellers booked on it."""
        counts: dict[str, int] = {}
        for b in self._bookings():
            for f in b.legs:
                counts[f.flight_id] = counts.get(f.flight_id, 0) + 1
        return counts

    def flight_care(self, flight_id: str) -> dict[str, Any]:
        """Every Groundtime traveller waiting for ``flight_id``, with their plan as customer
        care sees it: what is planned and that it suits them, not their dietary needs."""
        flight = self._flight(flight_id)
        now, delays = self.clock(), self.delays()
        waiting = [
            (booked, wait)
            for booked in self._bookings()
            if (wait := ground_wait(booked.legs, booked.position, now, delays)) is not None
            and wait.flight.flight_id == flight_id
        ]

        def row(pair: tuple[Booked, GroundWait]) -> dict[str, Any]:
            booked, wait = pair
            plan = plan_groundtime(wait, self.taste(booked.traveller_id), self.qloo)
            return {"name": booked.name} | plan.to_dict(for_traveller=False)

        with ThreadPoolExecutor(max_workers=max(1, min(8, len(waiting)))) as pool:
            rows = list(pool.map(row, waiting))
        modes = {m: sum(r["wait"]["mode"] == m for r in rows) for m in ("city", "terminal")}
        return {
            "flight_id": flight_id,
            "flight_no": flight.flight_no,
            "from": flight.dep_station,
            "to": flight.arr_station,
            "delay_minutes": self.delays().get(flight_id, 0),
            "travellers": rows,
            "by_mode": modes,
            "booked": flight.booked,
            "note": (
                "Only passengers with Groundtime are planned here; the rest of those booked "
                "are counted, never named."
            ),
        }

    def delayed_flights(self) -> list[dict[str, Any]]:
        """Delayed flights still to leave, earliest first."""
        now = self.clock()
        flights = self.flights()
        records = self._delay_records()
        counts = self._counts()
        out = []
        for flight_id, minutes in self.delays().items():
            flight = flights.get(flight_id)
            if flight is None or minutes <= 0:
                continue
            expected = flight.dep_utc + timedelta(minutes=minutes)
            if expected <= now:
                continue
            out.append(
                {
                    "flight_id": flight_id,
                    "flight_no": flight.flight_no,
                    "from": flight.dep_station,
                    "to": flight.arr_station,
                    "scheduled_utc": _iso(flight.dep_utc),
                    "departs_local": _local(flight.dep_utc),
                    "expected_departure_local": _local(expected),
                    "delay_minutes": minutes,
                    "booked": flight.booked,
                    "with_app": counts.get(flight_id, 0),
                }
                | _delay_view(records.get(flight_id))
            )
        return sorted(out, key=lambda r: r["scheduled_utc"])


def _from_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _delay_view(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """What customer care sees of a flight's delay record: the latest change, who made it
    and when (local time), how many times it has been marked late, and every change."""
    record = record or {}
    times = int(record.get("times") or 0)
    history = [
        {
            "delay_minutes": int(h.get("minutes") or 0),
            "reason": h.get("reason"),
            "by": h.get("by"),
            "at_local": _local(_from_iso(h["at"])) if h.get("at") else None,
        }
        for h in record.get("history") or ()
    ]
    return {
        "reason": record.get("reason"),
        "recorded_by": record.get("recorded_by"),
        "recorded_local": (
            _local(_from_iso(record["recorded_utc"])) if record.get("recorded_utc") else None
        ),
        "first_delayed_local": next(
            (h["at_local"] for h in history if h["delay_minutes"] > 0), None
        ),
        "times_delayed": times,
        "delays_left": max(0, MAX_DELAY_TIMES - times),
        "history": history,
    }


def _without_owner(profile: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in profile.items() if k != "crew_id"}
