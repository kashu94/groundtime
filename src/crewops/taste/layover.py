"""Layover care: where a crew on a night stop can eat tonight, chosen for them.

A night stop is a duty day that ends away from where the next one starts from home: the crew
sleeps at an outstation. Night stops come from the pairings; a delay recorded on the day's
last flight pushes the release, and so the whole evening, later.

The brief has three sources and keeps them apart:

* the crew trip gives the window (``crewops.taste.window``): when the crew is free and when they
  must be asleep;
* Qloo gives the places near the crew hotel, ranked by taste affinity to what this crew loves
  (the Insights API with the crew's picks as signals), plus a second list filtered to the
  dietary options the crew needs;
* the checks here keep only places open for a whole meal in the window, offering every
  dietary option someone in the crew needs, not loud after a tiring day, not airside, and
  within reach. Every pick says why, every rejection is counted.

No model is involved, so the same trip and the same Qloo answer always give the same brief.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from crewops.taste.profile import DIETARY, TasteProfile
from crewops.taste.qloo import QlooClient
from crewops.taste.stations import CrewHotel, hotel_at
from crewops.taste.venues import DIETARY_TAG, Venue, venues_from_insights
from crewops.taste.window import MEAL, LayoverWindow, layover_window

PLACE = "urn:entity:place"
RESTAURANT = "urn:tag:genre:place:restaurant"
MAX_SIGNALS = 10
"""Loves sent to Qloo at most, for one crew. More dilutes the signal."""
TAKE = 15
PICKS = 3
MIN_REST_HOURS = 12.0
"""Minimum rest between release and the next report."""
TIRED_RADIUS_M = 1500


class LayoverError(Exception):
    """The layover can't be planned: something about the stop itself, not Qloo."""


@dataclass(frozen=True, slots=True)
class NightStop:
    pairing_id: str
    date: date
    """The duty day that ends at the outstation."""
    station: str
    release_utc: datetime
    next_report_utc: datetime
    crew_ids: tuple[str, ...]
    duty_hours: float | None = None
    cause: str = "rostered"
    """``rostered``, or ``delay`` when a recorded delay moved the release."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pairing_id": self.pairing_id,
            "date": self.date.isoformat(),
            "station": self.station,
            "release_utc": self.release_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "next_report_utc": self.next_report_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "crew_count": len(self.crew_ids),
            "duty_hours": self.duty_hours,
            "cause": self.cause,
        }


def night_stops(
    network: Any,
    *,
    pairing_id: str | None = None,
    crew_id: str | None = None,
    on: date | None = None,
    delays: Mapping[str, int] | None = None,
) -> list[NightStop]:
    """Rostered night stops, optionally for one pairing, one crew member or one date. A delay
    recorded on the day's last leg moves the release with it, so the rest starts later."""
    delays = delays or {}
    out: list[NightStop] = []
    if pairing_id:
        pairings = [network.pairings[pairing_id]] if pairing_id in network.pairings else []
    else:
        pairings = list(network.pairings.values())
    for pairing in pairings:
        crew = tuple(seat.crew_id for seat in pairing.crew)
        if crew_id and crew_id not in crew:
            continue
        days = pairing.days
        for today, tomorrow in zip(days, days[1:], strict=False):
            if on and today.date != on:
                continue
            last = network.flights.get(today.flight_ids[-1])
            if last is None:
                continue
            late = timedelta(minutes=delays.get(last.flight_id, 0))
            release = today.release_utc + late
            out.append(
                NightStop(
                    pairing_id=pairing.pairing_id,
                    date=today.date,
                    station=last.arr_station,
                    release_utc=release,
                    next_report_utc=tomorrow.report_utc,
                    crew_ids=crew,
                    duty_hours=round((release - today.report_utc).total_seconds() / 3600, 2),
                    cause="delay" if late else "rostered",
                )
            )
    return sorted(out, key=lambda s: (s.release_utc, s.pairing_id))


@dataclass(frozen=True, slots=True)
class Pick:
    venue: Venue
    why: tuple[str, ...]
    open_until: str | None

    def to_dict(self) -> dict[str, Any]:
        return self.venue.to_dict() | {"why": list(self.why), "open_until": self.open_until}


@dataclass(frozen=True, slots=True)
class LayoverBrief:
    stop: NightStop
    window: LayoverWindow
    picks: tuple[Pick, ...]
    considered: int
    rejected: Mapping[str, int]
    """Reason -> how many places Qloo offered were left out for it."""
    taste_shared_by: int
    """Crew members whose picks were sent as signals (never who they are)."""
    dietary_needed: frozenset[str]
    quiet: bool
    radius_m: int
    signals: int
    note: str | None = None
    source: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self, *, for_crew: bool = False) -> dict[str, Any]:
        """``for_crew`` is the crew member's own view and may name their dietary needs. The
        staff view only says the needs are all met, so no one's diet is shown."""
        out = {
            "night_stop": self.stop.to_dict(),
            "window": self.window.to_dict(),
            "picks": [p.to_dict() for p in self.picks],
            "considered": self.considered,
            "rejected": dict(self.rejected),
            "taste_shared_by": self.taste_shared_by,
            "crew_count": len(self.stop.crew_ids),
            "dietary_needs_met": bool(self.picks) or not self.dietary_needed,
            "quiet": self.quiet,
            "radius_m": self.radius_m,
            "note": self.note,
            "source": dict(self.source),
        }
        if for_crew:
            out["dietary_needed"] = sorted(self.dietary_needed)
        return out


def _signals(profiles: Iterable[TasteProfile]) -> tuple[list[str], list[str]]:
    """Entity and tag ids, the ones more of the crew share first."""
    counts: Counter[str] = Counter()
    for profile in profiles:
        counts.update({love.id for love in profile.loves})
    ordered = [i for i, _ in counts.most_common(MAX_SIGNALS)]
    return [i for i in ordered if not i.startswith("urn:tag:")], [
        i for i in ordered if i.startswith("urn:tag:")
    ]


def _quiet(window: LayoverWindow, profiles: list[TasteProfile]) -> bool:
    if window.tiring:
        return True
    votes = Counter(p.wind_down for p in profiles if p.wind_down)
    return votes["quiet"] > votes["lively"]


def _food(option: str) -> str:
    """``jain`` -> ``Jain``, ``gluten_free`` -> ``gluten-free``: as written mid-sentence."""
    label = DIETARY[option]
    return label if option in ("jain",) else label.lower()


def _why(
    venue: Venue, window: LayoverWindow, needed: frozenset[str], quiet: bool, signals: int
) -> tuple[str, ...]:
    reasons = []
    if window.meal_at is not None:
        until = venue.closes_after(window.meal_at)
        reasons.append(
            f"Open at {window.meal_at:%H:%M}" + (f", until {until:%H:%M}" if until else "")
        )
    if venue.distance_m is not None:
        reasons.append(f"{round(venue.distance_m / 50) * 50:.0f} m from the crew hotel")
    if needed:
        reasons.append("Offers " + ", ".join(_food(d) for d in sorted(needed)) + " food")
    if quiet and venue.noise == "quiet":
        reasons.append("Quiet, for a tired crew")
    if venue.genres:
        reasons.append(", ".join(g for g in venue.genres if g not in ("Place", "Restaurant"))[:80])
    return tuple(r for r in reasons if r)


def _fetch(
    qloo: QlooClient,
    hotel: CrewHotel,
    radius: int,
    entities: list[str],
    tags: list[str],
    needed: frozenset[str],
) -> tuple[list[Venue], list[dict[str, str]]]:
    base: dict[str, Any] = {
        "filter.type": PLACE,
        "filter.location": hotel.point,
        "filter.location.radius": radius,
        "take": TAKE,
    }
    requests = [
        base
        | {
            "filter.tags": RESTAURANT,
            "signal.interests.entities": entities or None,
            "signal.interests.tags": tags or None,
        }
    ]
    if needed:
        # A second list filtered by one dietary tag, so places offering it aren't crowded out
        # of the first; every need is still checked on every place afterwards.
        requests.append(
            base
            | {
                "filter.tags": f"{DIETARY_TAG}{sorted(needed)[0]}",
                "signal.interests.entities": entities or None,
                "signal.interests.tags": tags or None,
            }
        )
    found: dict[str, Venue] = {}
    for params in requests:
        for venue in venues_from_insights(qloo.insights(params)):
            found.setdefault(venue.entity_id, venue)
    shown = [
        {k: str(v) for k, v in params.items() if v is not None and not k.startswith("signal.")}
        | ({"signals": f"{len(entities) + len(tags)} taste ids"} if entities or tags else {})
        for params in requests
    ]
    return list(found.values()), shown


def layover_brief(
    stop: NightStop,
    profiles: Mapping[str, TasteProfile],
    qloo: QlooClient,
    *,
    min_rest_hours: float = MIN_REST_HOURS,
) -> LayoverBrief:
    """The brief for ``stop``. ``profiles`` holds the taste profiles of whichever of its crew
    have one; for a crew member's own brief, pass only theirs."""
    hotel = hotel_at(stop.station)
    if hotel is None:
        raise LayoverError(f"no crew hotel is set up at {stop.station}")
    window = layover_window(
        hotel,
        stop.release_utc,
        stop.next_report_utc,
        min_rest_hours=min_rest_hours,
        duty_hours=stop.duty_hours,
    )
    members = [profiles[c] for c in stop.crew_ids if c in profiles and not profiles[c].empty]
    entities, tags = _signals(members)
    needed = frozenset().union(*(p.dietary for p in members)) if members else frozenset()
    quiet = _quiet(window, members)
    radius = min(hotel.radius_m, TIRED_RADIUS_M) if window.tiring else hotel.radius_m
    common = {
        "stop": stop,
        "window": window,
        "taste_shared_by": sum(1 for p in members if p.loves),
        "dietary_needed": needed,
        "quiet": quiet,
        "radius_m": radius,
        "signals": len(entities) + len(tags),
    }
    short_rest = (
        None
        if window.legal_rest
        else f"This rest is shorter than the {min_rest_hours:g}-hour minimum: tell crew "
        "scheduling before you plan anything."
    )
    if window.meal_at is None:
        note = (
            "No time for a meal out: rest comes first. Order in at the hotel and keep "
            f"the sleep before the {window.sleep_by:%H:%M} cut-off."
        )
        return LayoverBrief(
            picks=(),
            considered=0,
            rejected={},
            note=f"{short_rest} {note}" if short_rest else note,
            **common,
        )
    venues, requests = _fetch(qloo, hotel, radius, entities, tags, needed)
    rejected: Counter[str] = Counter()
    kept: list[tuple[tuple[Any, ...], Venue]] = []
    for venue in venues:
        if venue.closed:
            rejected["closed for good"] += 1
            continue
        if venue.airside:
            rejected["airside or food court"] += 1
            continue
        if venue.distance_m is not None and venue.distance_m > radius:
            rejected["too far"] += 1
            continue
        is_open = venue.open_through(window.meal_at, int(MEAL.total_seconds() // 60))
        if is_open is False:
            rejected[f"closed at {window.meal_at:%H:%M} or too soon after"] += 1
            continue
        if not needed <= venue.dietary:
            rejected["missing a dietary option the crew needs"] += 1
            continue
        if quiet and venue.noise == "loud":
            rejected["loud, after a tiring day" if window.tiring else "loud"] += 1
            continue
        rank = (
            is_open is None,  # listed hours beat unknown hours
            quiet and venue.noise != "quiet",
            -(venue.affinity if venue.affinity is not None else 0.0),
            -(venue.rating or 0.0),
            venue.distance_m if venue.distance_m is not None else float("inf"),
            venue.name,
        )
        kept.append((rank, venue))
    kept.sort(key=lambda pair: pair[0])
    picks = tuple(
        Pick(
            venue=v,
            why=_why(v, window, needed, quiet, len(entities) + len(tags))
            + (("Opening hours not listed: call ahead",) if rank[0] else ()),
            open_until=(lambda t: None if t is None else f"{t:%H:%M}")(
                v.closes_after(window.meal_at)
            ),
        )
        for rank, v in kept[:PICKS]
    )
    note = short_rest
    if not picks:
        empty = (
            "Nothing near the crew hotel fits tonight. Order in at the hotel, or ask the "
            "station duty manager for a late kitchen."
        )
        note = f"{note} {empty}" if note else empty
    return LayoverBrief(
        picks=picks,
        considered=len(venues),
        rejected=dict(rejected),
        note=note,
        source={"provider": "Qloo Insights API", "requests": requests},
        **common,
    )
