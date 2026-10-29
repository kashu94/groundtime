"""Groundtime as the server offers it: whose trip, which delays, and the plan.

The MCP server and the concierge share this. It knows the traveller from the signed-in user
(never from what they type), takes every delay from the disruptions reported on the live
operation, and keeps taste profiles in the operations table.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from crewops.store.reports import disruptions_with_status
from crewops.store.taste import profile_of, save_profile
from crewops.taste.groundtime import GroundPlan, GroundWait, ground_wait, plan_groundtime
from crewops.taste.profile import LOVE_TYPES, TasteProfile
from crewops.taste.qloo import QlooClient
from crewops.taste.travellers import Position, Traveller, load_travellers, trip

DISRUPTION_STATUSES = (
    "REPORTED", "OPTIONS_READY", "SUBMITTED", "COMMITTED", "RESOLVING", "CLOSED",
)  # fmt: skip
"""Every state a reported delay can be in and still be true. Only a revoked one is not."""
DELAY_CACHE_SECONDS = 30.0
SEARCH_TYPES = {k for k in LOVE_TYPES if k != "urn:tag"}


class GroundtimeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def flight_delays(table: Any) -> dict[str, int]:
    """Flight id -> minutes late, from reported delays. The latest report for a flight wins."""
    latest: dict[str, tuple[str, int]] = {}
    for status in DISRUPTION_STATUSES:
        for item in disruptions_with_status(table, status):
            report = item.get("report") or {}
            if report.get("type") != "flight_delay":
                continue
            details = report.get("details") or {}
            flight_id, minutes = details.get("flight_id"), details.get("delay_minutes")
            if not flight_id or minutes is None:
                continue
            at = str(report.get("reported_utc") or "")
            if flight_id not in latest or at > latest[flight_id][0]:
                latest[flight_id] = (at, int(minutes))
    return {f: m for f, (_, m) in latest.items()}


def _without_owner(profile: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in profile.items() if k != "crew_id"}


class Groundtime:
    def __init__(
        self,
        table: Any,
        qloo: QlooClient,
        flights: Callable[[], Mapping[str, Any]],
        *,
        clock: Callable[[], datetime],
        travellers: Mapping[str, Traveller] | None = None,
        delays: Callable[[], Mapping[str, int]] | None = None,
    ) -> None:
        """``flights`` gives the live operation's flights by id; ``delays`` defaults to the
        reported delays in ``table``."""
        self.table = table
        self.qloo = qloo
        self.flights = flights
        self.clock = clock
        self.travellers = dict(travellers) if travellers is not None else load_travellers()
        self._delays = delays
        self._delay_cache: tuple[float, dict[str, int]] | None = None
        self._lock = threading.Lock()

    # -- Who and when ----------------------------------------------------------

    def traveller(self, username: str) -> Traveller:
        found = self.travellers.get(username)
        if found is None:
            raise GroundtimeError("NOT_FOUND", "no booking is linked to this account")
        return found

    def delays(self) -> dict[str, int]:
        if self._delays is not None:
            return dict(self._delays())
        with self._lock:
            if self._delay_cache and time.monotonic() - self._delay_cache[0] < DELAY_CACHE_SECONDS:
                return self._delay_cache[1]
        found = flight_delays(self.table)
        with self._lock:
            self._delay_cache = (time.monotonic(), found)
        return found

    def taste(self, traveller: Traveller) -> TasteProfile:
        """The traveller's saved profile, else the one their booking came with."""
        saved = profile_of(self.table, traveller.traveller_id)
        return saved if saved is not None else traveller.taste

    def wait(self, traveller: Traveller, position: str | None = None) -> GroundWait:
        try:
            where = Position(position) if position else traveller.position
        except ValueError:
            raise GroundtimeError("INVALID", "position must be away, landside or airside") from None
        now = self.clock()
        legs = trip(self.flights(), traveller.flight_nos, now)
        if not legs:
            raise GroundtimeError("NOT_FOUND", "no upcoming flight on this booking")
        found = ground_wait(legs, where, now, self.delays())
        if found is None:
            raise GroundtimeError("NOT_FOUND", "every flight on this booking has left")
        return found

    def plan(self, traveller: Traveller, position: str | None = None) -> GroundPlan:
        return plan_groundtime(self.wait(traveller, position), self.taste(traveller), self.qloo)

    # -- The traveller's own view ----------------------------------------------

    def my_plan(self, username: str, position: str | None = None) -> dict[str, Any]:
        traveller = self.traveller(username)
        plan = self.plan(traveller, position)
        return {"traveller": {"name": traveller.name}} | plan.to_dict(for_traveller=True)

    def my_taste(self, username: str) -> dict[str, Any]:
        traveller = self.traveller(username)
        return _without_owner(self.taste(traveller).to_dict())

    def save_my_taste(self, username: str, body: Mapping[str, Any]) -> dict[str, Any]:
        traveller = self.traveller(username)
        profile = TasteProfile.from_dict(traveller.traveller_id, body)
        saved = save_profile(self.table, profile, self.clock())
        return _without_owner(saved.to_dict())

    def search(self, query: str, kind: str) -> list[dict[str, Any]]:
        """Qloo's own catalogue, for picking what you love: an id, never free text."""
        query = (query or "").strip()
        if not 2 <= len(query) <= 80:
            raise GroundtimeError("INVALID", "search for 2 to 80 characters")
        if kind not in SEARCH_TYPES:
            kinds = ", ".join(sorted(SEARCH_TYPES))
            raise GroundtimeError("INVALID", f"kind must be one of {kinds}")
        body = self.qloo.search(query, kind, take=6)
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

    # -- Customer care ---------------------------------------------------------

    def flight_care(self, flight_id: str) -> dict[str, Any]:
        """Every booked traveller waiting for ``flight_id``, with their plan as customer care
        sees it: what is planned and that it suits them, not their dietary needs."""
        flight = self.flights().get(flight_id)
        if flight is None:
            raise GroundtimeError("NOT_FOUND", f"no flight {flight_id}")
        rows = []
        for traveller in self.travellers.values():
            try:
                wait = self.wait(traveller)
            except GroundtimeError:
                continue
            if wait.flight.flight_id != flight_id:
                continue
            plan = plan_groundtime(wait, self.taste(traveller), self.qloo)
            rows.append(
                {"name": traveller.name, "username": traveller.username}
                | plan.to_dict(for_traveller=False)
            )
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
                "Only passengers with the app are planned here; the rest of those booked are "
                "counted, never named."
            ),
        }

    def delayed_flights(self) -> list[dict[str, Any]]:
        """Delayed flights still to leave, latest departure last."""
        now = self.clock()
        flights = self.flights()
        out = []
        for flight_id, minutes in self.delays().items():
            flight = flights.get(flight_id)
            if flight is None or minutes <= 0:
                continue
            expected = flight.dep_utc.timestamp() + minutes * 60
            if expected <= now.timestamp():
                continue
            waiting = sum(1 for t in self.travellers.values() if flight.flight_no in t.flight_nos)
            out.append(
                {
                    "flight_id": flight_id,
                    "flight_no": flight.flight_no,
                    "from": flight.dep_station,
                    "to": flight.arr_station,
                    "scheduled_utc": flight.dep_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "delay_minutes": minutes,
                    "booked": flight.booked,
                    "with_app": waiting,
                }
            )
        return sorted(out, key=lambda r: r["scheduled_utc"])
