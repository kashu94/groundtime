"""Groundtime: what a passenger can do with a wait, planned with Qloo and checked here.

Three sources, kept apart as in the crew layover brief:

* the schedule gives the wait (``ground_wait``): when the traveller is free, when they must be
  at the terminal door and at the gate, and whether an outing is possible at all. Someone
  already at the airport stays in the terminal, as does anyone connecting; someone who hasn't
  left for the airport yet can spend the delay near it, on their way in, if the time allows;
* Qloo gives the candidates, ranked by taste affinity to what the traveller loves: places to
  see and to eat around the airport, places in the terminal, and films and series;
* the checks here keep only what fits: a sight that is a real sight (Qloo tags hotels and
  travel agents as attractions too), open for the whole visit, a meal that offers every
  dietary option the traveller needs, an outing that is back at the terminal in time with the
  ride both ways counted, a film short enough to finish before the gate closes.

No model is involved. The same schedule and the same Qloo answers always give the same plan,
and every stop says why it was chosen.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from crewops.domain.models import Flight
from crewops.taste.layover import _food
from crewops.taste.profile import TasteProfile
from crewops.taste.qloo import QlooClient, QlooError
from crewops.taste.stations import Airport, airport_at
from crewops.taste.travellers import Position
from crewops.taste.venues import DIETARY_TAG, Venue, venues_from_insights

PLACE = "urn:entity:place"
SIGHT_TAGS = ",".join(
    f"urn:tag:genre:place:{g}"
    for g in ("museum", "park", "beach", "market", "tourist_attraction", "monument", "art_gallery")
)
MEAL_TAGS = "urn:tag:genre:place:restaurant"
TERMINAL_TAGS = "urn:tag:genre:place:restaurant,urn:tag:genre:place:cafe"
SIGHTS = {
    "art gallery", "beach", "botanical garden", "church", "cultural center", "fortress",
    "garden", "heritage museum", "historical landmark", "hindu temple", "live music venue",
    "market", "monument", "museum", "park", "performing arts theater", "temple",
    "tourist attraction", "view point", "war memorial", "heritage preservation",
}  # fmt: skip
"""Genres that make a place worth a visit. One is enough, as long as none below applies."""
NOT_A_SIGHT = {
    "hotel", "motel", "resort hotel", "serviced apartment", "car rental agency",
    "travel agency", "tour agency", "tour operator", "cruise agency", "government office",
    "wedding venue", "banquet hall", "real estate agency", "dive shop",
    "scuba tour agency", "event venue", "corporate office", "stadium",
}  # fmt: skip
EATERY = {
    "restaurant", "cafe", "coffee shop", "food court", "bakery", "fast food", "breakfast",
    "south indian restaurant", "north indian", "indian", "tea house", "dessert shop",
}  # fmt: skip
NOT_AN_EATERY = {"hotel", "lounge bar", "duty free store", "government office"}

TAKE = 15
SIGHT_MINUTES = 60
MEAL_MINUTES = 60
TERMINAL_MEAL_MINUTES = 40
MIN_OUTING_MINUTES = 90
"""Less than this outside, after the rides, is not worth leaving the terminal for."""
BUFFER = timedelta(minutes=15)
"""Slack before each deadline: the terminal door, and the gate."""
DEPLANE = timedelta(minutes=15)
ROAD_FACTOR = 1.4
"""Road distance over straight-line distance, in an Indian city."""
CITY_KMH = 25.0
PICKUP_MINUTES = 10
"""Finding a cab or an auto."""
TERMINAL_RADIUS_M = 900
WATCH_MARGIN_MINUTES = 20


def ride_minutes(metres: float) -> int:
    """A deliberately cautious ride estimate: road distance at city speed, plus a pickup."""
    km = metres * ROAD_FACTOR / 1000
    return math.ceil(km / CITY_KMH * 60) + PICKUP_MINUTES


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _round5(t: datetime) -> datetime:
    """Up to the next five minutes: nobody plans to arrive at 14:52."""
    return (t + timedelta(minutes=(-t.minute) % 5)).replace(second=0, microsecond=0)


def _local(t: datetime | None) -> str | None:
    return None if t is None else t.strftime("%Y-%m-%d %H:%M")


@dataclass(frozen=True, slots=True)
class GroundWait:
    airport: Airport
    flight: Flight
    """The flight the traveller is waiting for."""
    delay_minutes: int
    position: Position
    connecting_from: Flight | None
    free_from: datetime
    """Local time the traveller's time is their own."""
    usual_terminal_by: datetime
    """Local time they'd have had to be at the terminal door without the delay."""
    at_terminal_by: datetime
    """Local time to be at the terminal door, before bag drop and security."""
    at_gate_by: datetime
    """Local time to be at the gate."""

    @property
    def expected_dep(self) -> datetime:
        return self.flight.dep_utc + timedelta(minutes=self.delay_minutes)

    @property
    def can_leave(self) -> bool:
        """Only someone who hasn't reached the airport yet. Once in the departure terminal,
        Indian airports let a passenger back out only with the airline's and security's
        clearance, and a connecting passenger stays airside."""
        return self.position is Position.AWAY and self.connecting_from is None

    @property
    def outside_minutes(self) -> int:
        """Time before they need to be at the terminal, rides included."""
        return max(0, int((self.at_terminal_by - self.free_from).total_seconds() // 60))

    @property
    def wait_minutes(self) -> int:
        """Time until the gate, for whatever is done without leaving."""
        return max(0, int((self.at_gate_by - self.free_from).total_seconds() // 60))

    @property
    def mode(self) -> str:
        """``city``: an outing around the airport; ``terminal``: stay and make the most of it."""
        if self.can_leave and self.outside_minutes >= MIN_OUTING_MINUTES:
            return "city"
        return "terminal"

    @property
    def stay_reason(self) -> str | None:
        if self.connecting_from is not None:
            return (
                "You're connecting, so you stay airside between flights: this plan is "
                "inside the terminal."
            )
        if self.position is Position.AIRPORT:
            return (
                "You're already at the airport. Indian airports only let a passenger back out "
                "of the departure terminal with the airline's and security's clearance, so "
                "this plan stays inside."
            )
        if self.mode == "terminal":
            return (
                f"There isn't enough time for an outing before you need to be at the "
                f"terminal by {self.at_terminal_by:%H:%M}, so this plan is at the airport."
            )
        return None

    @property
    def staff_summary(self) -> str:
        """The wait as customer care reads it: where they are and the deadline that matters."""
        gate = f"at the gate by {self.at_gate_by:%H:%M}"
        if self.connecting_from is not None:
            return f"Connecting at {self.airport.city}: stays airside, {gate}."
        if self.position is Position.AIRPORT:
            return f"At the airport: a plan inside the terminal, {gate}."
        terminal = f"at the terminal by {self.at_terminal_by:%H:%M}"
        if self.mode == "city":
            return f"Not at the airport yet: an outing near it on the way in, {terminal}."
        return f"Not at the airport yet: {terminal}."

    @property
    def headline(self) -> str:
        """The wait in plain words: where they are, what changed, and by when."""
        no = self.flight.flight_no
        late = f"{no} is {late_by(self.delay_minutes)} late" if self.delay_minutes else None
        gate = f"be at the gate by {self.at_gate_by:%H:%M}"
        if self.connecting_from is not None:
            first = f"You're connecting at {self.airport.city} for {no}"
            if self.delay_minutes:
                first += f", which is {late_by(self.delay_minutes)} late"
            return f"{first}. Stay airside and {gate}; until then, here's your time inside."
        if self.position is Position.AIRPORT:
            first = f"You're at {self.airport.city} airport. " + (
                f"{late}, so {gate}." if late else f"{no} is on time: {gate}."
            )
            return f"{first} Until then, here's what to do inside the terminal."
        if not late:
            return f"No delay on {no}: be at the terminal by {self.at_terminal_by:%H:%M}."
        if self.mode == "city":
            return (
                f"You haven't left for the airport yet. {late}, so instead of being at the "
                f"airport at {self.usual_terminal_by:%H:%M}, here's what to do near it on your "
                f"way in, before you need to be at the terminal by {self.at_terminal_by:%H:%M}."
            )
        return (
            f"You haven't left for the airport yet. {late}: be at the terminal by "
            f"{self.at_terminal_by:%H:%M}. There isn't time for an outing first, so here's "
            "what to do once you're there."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "station": self.airport.station,
            "city": self.airport.city,
            "airport": self.airport.name,
            "flight_id": self.flight.flight_id,
            "flight_no": self.flight.flight_no,
            "to": self.flight.arr_station,
            "scheduled_departure_local": _local(self.flight.dep_utc.astimezone(self.airport.tz)),
            "expected_departure_local": _local(self.expected_dep.astimezone(self.airport.tz)),
            "delay_minutes": self.delay_minutes,
            "connecting_from": self.connecting_from.flight_id if self.connecting_from else None,
            "position": self.position.value,
            "can_leave": self.can_leave,
            "mode": self.mode,
            "stay_reason": self.stay_reason,
            "headline": self.headline,
            "staff_summary": self.staff_summary,
            "free_from_local": _local(self.free_from),
            "usual_terminal_by_local": _local(self.usual_terminal_by),
            "at_terminal_by_local": _local(self.at_terminal_by),
            "at_gate_by_local": _local(self.at_gate_by),
            "outside_minutes": self.outside_minutes if self.can_leave else 0,
            "wait_minutes": self.wait_minutes,
            "timezone": self.airport.tz.tzname(None),
        }


def ground_wait(
    legs: tuple[Flight, ...],
    position: Position,
    now: datetime,
    delays: Mapping[str, int] | None = None,
) -> GroundWait | None:
    """The traveller's current wait on a trip, or None when every leg has left.

    Before the first leg they wait where they told us they are. Between legs they are
    connecting: at the airport, airside, from their arrival. A delay moves the departure. For
    someone not yet at the airport the free time starts when they would otherwise have had to
    be at the terminal, so the delay is time handed back, not time spent at the airport; for
    someone already there it starts now.
    """
    delays = delays or {}
    for i, leg in enumerate(legs):
        expected = leg.dep_utc + timedelta(minutes=delays.get(leg.flight_id, 0))
        if expected <= now:
            continue
        airport = airport_at(leg.dep_station)
        if airport is None:
            return None
        before = legs[i - 1] if i else None
        security = timedelta(minutes=airport.security_minutes)
        usual = leg.dep_utc - _to_gate(airport) - security - BUFFER
        if before is not None:
            here = Position.AIRPORT
            arrived = before.arr_utc + timedelta(minutes=delays.get(before.flight_id, 0))
            start = arrived + DEPLANE
        else:
            here = position
            start = now if here is Position.AIRPORT else usual
        at_gate_by = expected - _to_gate(airport)
        at_terminal_by = at_gate_by - security - BUFFER
        return GroundWait(
            airport=airport,
            flight=leg,
            delay_minutes=delays.get(leg.flight_id, 0),
            position=here,
            connecting_from=before,
            free_from=max(start, now).astimezone(airport.tz),
            usual_terminal_by=usual.astimezone(airport.tz),
            at_terminal_by=at_terminal_by.astimezone(airport.tz),
            at_gate_by=at_gate_by.astimezone(airport.tz),
        )
    return None


def late_by(minutes: int) -> str:
    """``240`` -> ``4 h``, ``150`` -> ``2 h 30 min``, ``45`` -> ``45 min``."""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} min"
    return f"{hours} h" + (f" {rest} min" if rest else "")


def _to_gate(airport: Airport) -> timedelta:
    return timedelta(minutes=airport.gate_close_minutes) + BUFFER


# ----------------------------------------------------------------------------
# The plan
# ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stop:
    venue: Venue
    kind: str
    """``sight``, ``meal`` or ``terminal`` (food or coffee without leaving)."""
    arrive: datetime
    leave: datetime
    ride_minutes: int
    """Ride to this stop; 0 in the terminal."""
    why: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return self.venue.to_dict() | {
            "kind": self.kind,
            "arrive_local": _local(self.arrive),
            "leave_local": _local(self.leave),
            "ride_minutes": self.ride_minutes,
            "why": list(self.why),
        }


@dataclass(frozen=True, slots=True)
class Watch:
    entity_id: str
    title: str
    kind: str
    """``film`` or ``series``."""
    minutes: int | None
    year: int | None
    affinity: float | None
    image: str | None
    why: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "title": self.title,
            "kind": self.kind,
            "minutes": self.minutes,
            "year": self.year,
            "affinity": None if self.affinity is None else round(self.affinity, 3),
            "image": self.image,
            "why": list(self.why),
        }


@dataclass(frozen=True, slots=True)
class GroundPlan:
    wait: GroundWait
    stops: tuple[Stop, ...]
    watch: tuple[Watch, ...]
    head_back_by: datetime | None
    """Local time to leave the last stop, in a city plan."""
    back_at_terminal: datetime | None
    considered: int
    rejected: Mapping[str, int]
    dietary_needed: frozenset[str]
    signals: int
    unavailable: tuple[str, ...] = ()
    """Parts Qloo could not answer this time; the rest of the plan still stands."""
    note: str | None = None
    source: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self, *, for_traveller: bool = True) -> dict[str, Any]:
        """``for_traveller`` names their dietary needs; the customer-care view only says
        whether every need is met."""
        out = {
            "wait": self.wait.to_dict(),
            "stops": [s.to_dict() for s in self.stops],
            "watch": [w.to_dict() for w in self.watch],
            "head_back_by_local": _local(self.head_back_by),
            "back_at_terminal_local": _local(self.back_at_terminal),
            "considered": self.considered,
            "rejected": dict(self.rejected),
            "dietary_needs_met": all(
                self.dietary_needed <= s.venue.dietary for s in self.stops if s.kind != "sight"
            ),
            "taste_shared": self.signals > 0,
            "unavailable": list(self.unavailable),
            "note": self.note,
            "source": dict(self.source),
        }
        if for_traveller:
            out["dietary_needed"] = sorted(self.dietary_needed)
        return out


def _names(v: Venue) -> set[str]:
    return {g.lower() for g in (*v.genres, *v.tags)}


def _is_sight(v: Venue) -> bool:
    names = _names(v)
    return bool(names & SIGHTS) and not names & NOT_A_SIGHT


def _is_eatery(v: Venue) -> bool:
    names = _names(v)
    return bool(names & EATERY) and not names & NOT_AN_EATERY


def _signals(taste: TasteProfile) -> dict[str, str | None]:
    entities = [love.id for love in taste.loves if not love.is_tag]
    tags = [love.id for love in taste.loves if love.is_tag]
    return {
        "signal.interests.entities": ",".join(entities) or None,
        "signal.interests.tags": ",".join(tags) or None,
    }


def _ask(
    qloo: QlooClient, requests: Mapping[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Every request at once (each can take seconds); a failed one is reported, not fatal."""
    answers: dict[str, dict[str, Any]] = {}
    failed: list[str] = []

    def one(name: str) -> tuple[str, dict[str, Any] | None]:
        try:
            return name, qloo.insights(requests[name])
        except QlooError:
            return name, None

    with ThreadPoolExecutor(max_workers=max(1, len(requests))) as pool:
        for name, body in pool.map(one, list(requests)):
            if body is None:
                failed.append(name)
            else:
                answers[name] = body
    return answers, sorted(failed)


def _venue_why(v: Venue, kind: str, at: datetime, needed: frozenset[str], signals: int) -> list:
    reasons = []
    until = v.closes_after(at)
    if until is not None:
        reasons.append(f"Open at {at:%H:%M}, until {until:%H:%M}")
    elif v.hours is None:
        reasons.append("Opening hours not listed: check before you go")
    if kind != "sight" and needed:
        reasons.append("Offers " + ", ".join(_food(d) for d in sorted(needed)) + " food")
    if signals and v.affinity is not None:
        reasons.append(f"Qloo taste match {v.affinity:.2f} with what you love")
    shown = [g for g in v.genres if g not in ("Place", "Restaurant", "Tourist attraction")]
    if shown:
        reasons.append(", ".join(shown[:3]))
    return reasons


def _rank(v: Venue) -> tuple[Any, ...]:
    return (
        v.hours is None,
        -(v.affinity if v.affinity is not None else 0.0),
        -(v.rating or 0.0),
        v.distance_m if v.distance_m is not None else float("inf"),
        v.name,
    )


def _watch(answers: Mapping[str, dict[str, Any]], minutes: int, signals: int) -> list[Watch]:
    """A film that ends before the gate, and a series whose episodes fit."""
    out: list[Watch] = []
    for name, kind in (("films", "film"), ("series", "series")):
        for e in (answers.get(name, {}).get("results") or {}).get("entities") or ():
            props = e.get("properties") or {}
            length = props.get("duration")
            length = int(length) if isinstance(length, int | float) else None
            if length is None or length > minutes - WATCH_MARGIN_MINUTES:
                continue
            affinity = (e.get("query") or {}).get("affinity")
            why = []
            if kind == "film":
                why.append(f"{length} min: over before your gate closes")
            else:
                episodes = (minutes - WATCH_MARGIN_MINUTES) // length
                why.append(f"{length}-min episodes: {episodes} fit before your gate")
            if signals and isinstance(affinity, int | float):
                why.append(f"Qloo taste match {affinity:.2f} with what you love")
            image = (props.get("image") or {}).get("url")
            out.append(
                Watch(
                    entity_id=str(e.get("entity_id")),
                    title=str(e.get("name")),
                    kind=kind,
                    minutes=length,
                    year=props.get("release_year"),
                    affinity=float(affinity) if isinstance(affinity, int | float) else None,
                    image=image if isinstance(image, str) else None,
                    why=tuple(why),
                )
            )
            break
    return out


def _verify(
    venues: list[Venue],
    is_kind: Callable[[Venue], bool],
    wrong_kind: str,
    needed: frozenset[str],
    radius: float,
    rejected: Counter[str],
) -> list[Venue]:
    kept = []
    for v in venues:
        if v.closed:
            rejected["closed for good"] += 1
        elif not is_kind(v):
            rejected[wrong_kind] += 1
        elif v.distance_m is not None and v.distance_m > radius:
            rejected["too far"] += 1
        elif needed and not needed <= v.dietary:
            rejected["missing a dietary option you need"] += 1
        else:
            kept.append(v)
    return sorted(kept, key=_rank)


def _outing(
    wait: GroundWait,
    sights: list[Venue],
    meals: list[Venue],
    rejected: Counter[str],
) -> tuple[list[tuple[Venue, str, datetime, datetime, int]], datetime | None, datetime | None]:
    """The best outing that gets them to the terminal in time: two stops if they fit, else one.

    Every candidate is walked through on the clock, from the time they'd have left for the
    airport: the ride there (counted from the airport, as the search is centred on it), the
    visit (the place must be open for all of it), the next ride, and the ride to the terminal.
    """
    airport = wait.airport
    home = (airport.lat, airport.lon)
    start = wait.free_from
    stays = {"sight": SIGHT_MINUTES, "meal": MEAL_MINUTES}
    options: list[list[tuple[Venue, str]]] = []
    for s in sights[:5]:
        options.append([(s, "sight")])
        for m in meals[:5]:
            options += [[(s, "sight"), (m, "meal")], [(m, "meal"), (s, "sight")]]
    options += [[(m, "meal")] for m in meals[:5]]

    best: tuple[tuple[Any, ...], list, datetime, datetime] | None = None
    too_late = closed = 0
    for option in options:
        t, here, legs, fits = start, home, [], True
        for venue, kind in option:
            if venue.lat is None or venue.lon is None:
                fits = False
                break
            ride = ride_minutes(_metres(here, (venue.lat, venue.lon)))
            arrive = _round5(t + timedelta(minutes=ride))
            if venue.open_through(arrive, stays[kind]) is False:
                closed += 1
                fits = False
                break
            leave = arrive + timedelta(minutes=stays[kind])
            legs.append((venue, kind, arrive, leave, ride))
            t, here = leave, (venue.lat, venue.lon)
        if not fits:
            continue
        back = t + timedelta(minutes=ride_minutes(_metres(here, home)))
        if back > wait.at_terminal_by:
            too_late += 1
            continue
        score = (
            -len(legs),
            sum(v.hours is None for v, *_ in legs),
            -sum(v.affinity or 0.0 for v, *_ in legs),
            back,
        )
        if best is None or score < best[0]:
            best = (score, legs, t, back)
    if too_late:
        rejected["would not be back at the terminal in time"] += too_late
    if closed:
        rejected["closed for part of the visit"] += closed
    if best is None:
        return [], None, None
    return best[1], best[2], best[3]


def plan_groundtime(wait: GroundWait, taste: TasteProfile, qloo: QlooClient) -> GroundPlan:
    """The plan for one traveller's wait."""
    airport = wait.airport
    signals = _signals(taste)
    n_signals = len(taste.loves)
    needed = taste.dietary
    city = wait.mode == "city"
    base = {"filter.type": PLACE, "filter.location": airport.point, "take": TAKE}
    requests: dict[str, dict[str, Any]] = {}
    if city:
        radius = airport.city_radius_m
        near = base | {"filter.location.radius": radius}
        requests["sights"] = near | {"filter.tags": SIGHT_TAGS} | signals
        requests["meals"] = near | {"filter.tags": MEAL_TAGS} | signals
    else:
        radius = TERMINAL_RADIUS_M
        requests["terminal"] = (
            base | {"filter.location.radius": radius, "filter.tags": TERMINAL_TAGS} | signals
        )
    if needed:
        requests["dietary"] = (
            base
            | {"filter.location.radius": radius}
            | {"filter.tags": f"{DIETARY_TAG}{sorted(needed)[0]}"}
            | signals
        )
    if n_signals:
        # Films for the wait, or for the flight when the wait is spent out.
        requests["films"] = {"filter.type": "urn:entity:movie", "take": 10} | signals
        requests["series"] = {"filter.type": "urn:entity:tv_show", "take": 10} | signals
    requests = {k: {p: v for p, v in r.items() if v is not None} for k, r in requests.items()}
    answers, failed = _ask(qloo, requests)

    def found(*names: str) -> list[Venue]:
        seen: dict[str, Venue] = {}
        for name in names:
            for v in venues_from_insights(answers.get(name, {})):
                seen.setdefault(v.entity_id, v)
        return list(seen.values())

    rejected: Counter[str] = Counter()
    stops: list[Stop] = []
    head_back = back = None
    considered = 0
    if city:
        sight_pool = found("sights")
        meal_pool = found("meals", "dietary")
        considered = len(sight_pool) + len(meal_pool)
        sights = _verify(
            sight_pool, _is_sight, "not a place to visit", frozenset(), radius, rejected
        )
        meals = _verify(meal_pool, _is_eatery, "not a place to eat", needed, radius, rejected)
        legs, head_back, back = _outing(wait, sights, meals, rejected)
        for venue, kind, arrive, leave, ride in legs:
            why = _venue_why(venue, kind, arrive, needed, n_signals)
            stops.append(Stop(venue, kind, arrive, leave, ride, tuple(why)))
    else:
        pool = found("terminal", "dietary")
        considered = len(pool)
        eateries = _verify(pool, _is_eatery, "not a place to eat", needed, radius, rejected)
        at = wait.free_from
        for v in eateries:
            if v.open_through(at, TERMINAL_MEAL_MINUTES) is False:
                rejected["closed now"] += 1
                continue
            why = _venue_why(v, "terminal", at, needed, n_signals)
            why.append("At the terminal: check it's on your side of security")
            stops.append(Stop(v, "terminal", at, at, 0, tuple(why)))
            if len(stops) == 2:
                break
    watch_minutes = wait.wait_minutes if not city else int(wait.flight.block_hours * 60)
    watch = _watch(answers, watch_minutes, n_signals)
    if city:
        watch = [
            Watch(w.entity_id, w.title, w.kind, w.minutes, w.year, w.affinity, w.image,
                  tuple(r.replace("before your gate closes", "within your flight")
                        .replace("before your gate", "on your flight") for r in w.why))
            for w in watch
        ]  # fmt: skip

    note = None
    if city and not stops:
        note = (
            "Nothing nearby fits the time and stays open long enough. Head to the airport "
            f"by {wait.at_terminal_by:%H:%M} and use the time there."
        )
    elif not city and not stops and not watch:
        note = "Nothing at the terminal matched this time. The gate opens as planned."
    if not n_signals:
        hint = "Share a few things you love to get picks made for you."
        note = f"{note} {hint}" if note else hint
    shown = {
        name: {k: v for k, v in params.items() if not k.startswith("signal.")}
        | ({"signals": f"{n_signals} taste ids"} if n_signals else {})
        for name, params in requests.items()
    }
    return GroundPlan(
        wait=wait,
        stops=tuple(stops),
        watch=tuple(watch),
        head_back_by=head_back,
        back_at_terminal=back,
        considered=considered,
        rejected=dict(rejected),
        dietary_needed=needed,
        signals=n_signals,
        unavailable=tuple(failed),
        note=note,
        source={"provider": "Qloo Insights API", "requests": shown},
    )
