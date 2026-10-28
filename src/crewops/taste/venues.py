"""Qloo place entities, shaped for the layover checks.

Qloo ranks places by taste; whether a place suits a tired crew tonight is checked here, from
what the entity itself says: its opening hours, its dietary options and its noise level. Each
check is deterministic, so a recommendation can always say why it was made, and a place
missing a fact (no hours listed, say) is ranked below one that has it rather than guessed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

DIETARY_TAG = "urn:tag:dietary_option:qloo:"
NOISE_TAG = "urn:tag:noise_level:qloo:"
AIRSIDE = {"airport", "airport lounge", "transit hub", "food court"}
"""Tags of places a crew leaving the airport can't use, or wouldn't choose for a sit-down meal."""


def _clock(text: Any) -> time | None:
    """``"T22:30:00"`` -> 22:30."""
    if not isinstance(text, str):
        return None
    try:
        return time.fromisoformat(text.removeprefix("T")[:8])
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Venue:
    entity_id: str
    name: str
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    distance_m: float | None = None
    affinity: float | None = None
    """Qloo's taste affinity to the signals sent, 0 to 1. None when no signal was sent."""
    popularity: float | None = None
    rating: float | None = None
    price_level: int | None = None
    hours: Mapping[str, tuple[tuple[time, time], ...]] | None = None
    """Weekday -> opening spans in local time. A day with no spans is closed. None: unknown."""
    dietary: frozenset[str] = frozenset()
    """Dietary options the place offers: vegetarian, vegan, jain, halal, gluten_free, ..."""
    noise: str | None = None
    """quiet, moderate or loud."""
    genres: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    """Readable tag names (cuisine, ambience, ...), for the reasons shown."""
    closed: bool = False
    image: str | None = None
    website: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def airside(self) -> bool:
        names = {t.lower() for t in (*self.genres, *self.tags)}
        return bool(names & AIRSIDE)

    def open_through(self, start: datetime, minutes: int) -> bool | None:
        """Open for the whole of ``minutes`` from ``start`` (local time)? None if unknown.

        A span that closes at or before it opens runs past midnight, so a place listed
        "18:00 to 02:00" on Friday is open at 01:00 on Saturday.
        """
        if self.hours is None:
            return None
        end = start + timedelta(minutes=minutes)
        for back in (0, 1):  # today's spans, and last night's running past midnight
            day = (start - timedelta(days=back)).date()
            for opens, closes in self.hours.get(WEEKDAYS[day.weekday()], ()):
                span_start = datetime.combine(day, opens, start.tzinfo)
                span_end = datetime.combine(day, closes, start.tzinfo)
                if span_end <= span_start:
                    span_end += timedelta(days=1)
                if span_start <= start and end <= span_end:
                    return True
        return False

    def closes_after(self, start: datetime) -> time | None:
        """When the span holding ``start`` ends, for "open until 01:00"."""
        if self.hours is None:
            return None
        for back in (0, 1):
            day = (start - timedelta(days=back)).date()
            for opens, closes in self.hours.get(WEEKDAYS[day.weekday()], ()):
                span_start = datetime.combine(day, opens, start.tzinfo)
                span_end = datetime.combine(day, closes, start.tzinfo)
                if span_end <= span_start:
                    span_end += timedelta(days=1)
                if span_start <= start < span_end:
                    return closes
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "address": self.address,
            "distance_m": None if self.distance_m is None else round(self.distance_m),
            "affinity": None if self.affinity is None else round(self.affinity, 3),
            "rating": self.rating,
            "price_level": self.price_level,
            "dietary": sorted(self.dietary),
            "noise": self.noise,
            "genres": list(self.genres),
            "image": self.image,
            "website": self.website,
        }


def _hours(raw: Any) -> dict[str, tuple[tuple[time, time], ...]] | None:
    if not isinstance(raw, Mapping) or not raw:
        return None
    out: dict[str, tuple[tuple[time, time], ...]] = {}
    for day in WEEKDAYS:
        spans = []
        for span in raw.get(day) or ():
            if not isinstance(span, Mapping) or span.get("closed"):
                continue
            opens, closes = _clock(span.get("opens")), _clock(span.get("closes"))
            if opens is not None and closes is not None:
                spans.append((opens, closes))
        out[day] = tuple(spans)
    if not any(out.values()):
        return None  # "closed every day" is how Qloo lists unknown hours for some places
    return out


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def venue_from_entity(entity: Mapping[str, Any]) -> Venue | None:
    """One Qloo place entity, or None if it has no id or name."""
    entity_id, name = entity.get("entity_id"), entity.get("name")
    if not isinstance(entity_id, str) or not isinstance(name, str):
        return None
    props = entity.get("properties") or {}
    query = entity.get("query") or {}
    location = entity.get("location") or {}
    tags = [t for t in entity.get("tags") or () if isinstance(t, Mapping)]
    dietary = frozenset(
        str(t["id"]).removeprefix(DIETARY_TAG)
        for t in tags
        if str(t.get("id", "")).startswith(DIETARY_TAG)
    )
    noise = next(
        (
            str(t["id"]).removeprefix(NOISE_TAG)
            for t in tags
            if str(t.get("id", "")).startswith(NOISE_TAG)
        ),
        None,
    )
    genres = tuple(
        str(t.get("name")) for t in tags if str(t.get("type", "")).startswith("urn:tag:genre")
    )
    readable = tuple(
        str(t.get("name"))
        for t in tags
        if any(
            str(t.get("type", "")).startswith(f"urn:tag:{kind}")
            for kind in ("cuisine", "ambience", "category", "specialty_dish", "time_of_day_fit")
        )
    )
    image = (props.get("image") or {}).get("url") or next(
        (i.get("url") for i in props.get("images") or () if isinstance(i, Mapping)), None
    )
    price = props.get("price_level")
    return Venue(
        entity_id=entity_id,
        name=name.strip(),
        address=props.get("address"),
        lat=_number(location.get("lat")),
        lon=_number(location.get("lon")),
        distance_m=_number(query.get("distance")),
        affinity=_number(query.get("affinity")),
        popularity=_number(entity.get("popularity")),
        rating=_number(props.get("business_rating")),
        price_level=int(price) if isinstance(price, int) and not isinstance(price, bool) else None,
        hours=_hours(props.get("hours")),
        dietary=dietary,
        noise=noise,
        genres=genres,
        tags=readable,
        closed=bool(props.get("is_closed")),
        image=image if isinstance(image, str) else None,
        website=props.get("website") if isinstance(props.get("website"), str) else None,
    )


def venues_from_insights(body: Mapping[str, Any]) -> list[Venue]:
    entities = ((body.get("results") or {}).get("entities")) or []
    return [v for v in (venue_from_entity(e) for e in entities if isinstance(e, Mapping)) if v]
