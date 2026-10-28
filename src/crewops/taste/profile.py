"""A crew member's taste profile: up to five things they love and what they can eat.

Opt-in and theirs alone. A crew member picks the things (an artist, a film, a book, a cuisine)
from Qloo's own catalogue, so each pick is a Qloo id, never free text. Controllers never see
whose picks are whose: a layover brief says only how many of the crew shared their taste and
that the pick meets everyone's dietary needs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_LOVES = 5

LOVE_TYPES = {
    "urn:entity:artist": "artist",
    "urn:entity:movie": "film",
    "urn:entity:tv_show": "TV show",
    "urn:entity:book": "book",
    "urn:entity:podcast": "podcast",
    "urn:entity:place": "place",
    "urn:tag": "cuisine or style",
}
"""What a pick can be, and how it's named on screen."""

DIETARY = {
    "vegetarian": "Vegetarian",
    "vegan": "Vegan",
    "jain": "Jain",
    "halal": "Halal",
    "gluten_free": "Gluten-free",
}
"""Dietary needs, keyed by Qloo's ``urn:tag:dietary_option:qloo:<key>`` tag."""

WIND_DOWN = ("quiet", "lively")

ENTITY_ID = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$", re.I)
TAG_ID = re.compile(r"^urn:tag:[a-z_]+(:[a-z0-9_]+)+$")


class ProfileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Love:
    id: str
    """A Qloo entity id, or a Qloo tag id (``urn:tag:...``) for a cuisine or a style."""
    name: str
    type: str

    @property
    def is_tag(self) -> bool:
        return self.id.startswith("urn:tag:")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "type": self.type}


@dataclass(frozen=True, slots=True)
class TasteProfile:
    crew_id: str
    loves: tuple[Love, ...] = ()
    dietary: frozenset[str] = frozenset()
    wind_down: str | None = None
    """How they like to unwind after a duty: ``quiet`` or ``lively``. None: no preference."""
    updated_utc: str | None = None

    @property
    def empty(self) -> bool:
        return not self.loves and not self.dietary and self.wind_down is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "crew_id": self.crew_id,
            "loves": [love.to_dict() for love in self.loves],
            "dietary": sorted(self.dietary),
            "wind_down": self.wind_down,
            "updated_utc": self.updated_utc,
        }

    @classmethod
    def from_dict(cls, crew_id: str, d: Mapping[str, Any]) -> TasteProfile:
        """Checks everything a crew member can send; raises ``ProfileError`` saying what."""
        raw_loves = d.get("loves") or []
        if not isinstance(raw_loves, list):
            raise ProfileError("loves must be a list")
        if len(raw_loves) > MAX_LOVES:
            raise ProfileError(f"pick at most {MAX_LOVES} things you love")
        loves: list[Love] = []
        for i, raw in enumerate(raw_loves):
            if not isinstance(raw, Mapping):
                raise ProfileError(f"loves[{i}] must be an object")
            love_id, name, kind = (str(raw.get(k) or "").strip() for k in ("id", "name", "type"))
            if not (ENTITY_ID.match(love_id) or TAG_ID.match(love_id)):
                raise ProfileError(f"loves[{i}]: {love_id!r} is not a Qloo id; pick from search")
            if kind not in LOVE_TYPES:
                raise ProfileError(f"loves[{i}]: unknown type {kind!r}")
            if not name or len(name) > 120:
                raise ProfileError(f"loves[{i}]: name must be 1 to 120 characters")
            if any(love.id == love_id for love in loves):
                continue
            loves.append(Love(love_id, name, kind))
        dietary = d.get("dietary") or []
        if not isinstance(dietary, list) or any(x not in DIETARY for x in dietary):
            raise ProfileError(f"dietary needs must be among {', '.join(DIETARY)}")
        wind_down = d.get("wind_down") or None
        if wind_down is not None and wind_down not in WIND_DOWN:
            raise ProfileError("wind_down must be quiet or lively")
        return cls(
            crew_id=crew_id,
            loves=tuple(loves),
            dietary=frozenset(dietary),
            wind_down=wind_down,
            updated_utc=d.get("updated_utc"),
        )
