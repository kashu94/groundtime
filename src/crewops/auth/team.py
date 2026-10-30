"""The team: who can sign in, with which roles, linked to which crew or passenger record.

The demo team lives in ``data/team/demo_team.json``: usernames, display names and roles,
and nothing private (no email, phone or password). It is checked before anything is
created: a crew login must name a real crew member under their own name, and a traveller
login a passenger record of its own.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crewops.domain import DataError, Role
from crewops.ingestion.seed import SeedData, default_seed_dir

USERNAME_RE = re.compile(r"^(?=.{3,32}$)[a-z][a-z0-9]*(?:\.[a-z0-9]+)?$")
"""firstname.lastname for staff (neha.joshi), crew id and surname for crew (c1042.nair),
traveller id and surname for travellers (tr1001.kapoor)."""
TRAVELLER_ID_RE = re.compile(r"^TR-\d{4}$")
CREW_NAME_RE = re.compile(r"^[A-Z]\.\s*[A-Z]|\b[A-Z]\.?$")
""""A. Nair", "A.Nair", "Nair A.": how crew are written, never how anyone else is."""
ALONE = frozenset({Role.CREW, Role.TRAVELLER})
"""A crew or traveller login is that person's own and holds no other role."""


@dataclass(frozen=True, slots=True)
class TeamMember:
    username: str
    name: str
    roles: frozenset[Role]
    crew_id: str | None = None
    traveller_id: str | None = None

    @classmethod
    def from_dict(cls, d: Any, ctx: str) -> TeamMember:
        if not isinstance(d, dict):
            raise DataError(f"{ctx}: expected an object")
        unknown = set(d) - {"username", "name", "roles", "crew_id", "traveller_id"}
        if unknown:
            raise DataError(f"{ctx}: unknown fields {sorted(unknown)}")
        username, name, roles = d.get("username"), d.get("name"), d.get("roles")
        if not isinstance(username, str) or not USERNAME_RE.match(username):
            raise DataError(
                f"{ctx}.username: 3-32 lowercase letters and digits, at most one dot, "
                f"got {username!r}"
            )
        if not isinstance(name, str) or not name.strip():
            raise DataError(f"{ctx}.name: required")
        if not isinstance(roles, list) or not roles:
            raise DataError(f"{ctx}.roles: a non-empty list")
        try:
            parsed = frozenset(Role(r) for r in roles)
        except ValueError:
            raise DataError(f"{ctx}.roles: unknown role in {roles}") from None
        return cls(username, name.strip(), parsed, d.get("crew_id"), d.get("traveller_id"))


def default_team_file() -> Path:
    return default_seed_dir().parent / "team" / "demo_team.json"


def load_team(path: Path | None = None) -> list[TeamMember]:
    doc = json.loads((path or default_team_file()).read_text(encoding="utf-8"))
    return [TeamMember.from_dict(m, f"members[{i}]") for i, m in enumerate(doc["members"])]


def validate_team(members: list[TeamMember], seed: SeedData) -> list[str]:
    """Every problem with the team, checked against the network. Empty means usable."""
    errors: list[str] = []
    crew = {c.crew_id: c for c in seed.crew}
    for field_name, values in (
        ("username", [m.username for m in members]),
        ("name", [m.name for m in members]),
        ("crew_id", [m.crew_id for m in members if m.crew_id]),
        ("traveller_id", [m.traveller_id for m in members if m.traveller_id]),
    ):
        for value, n in Counter(values).items():
            if n > 1:
                errors.append(f"{field_name} {value!r} is used by {n} members")
    for m in members:
        who = m.username
        if m.roles & ALONE and len(m.roles) > 1:
            errors.append(f"{who}: a crew or traveller login holds no other role")
        if Role.CREW in m.roles:
            record = crew.get(m.crew_id or "")
            if record is None:
                errors.append(f"{who}: crew login needs the crew id of a real crew member")
            elif record.name != m.name:
                errors.append(f"{who}: {m.crew_id} is {record.name}, not {m.name}")
        elif m.crew_id:
            errors.append(f"{who}: only a crew login is linked to a crew id")
        if Role.TRAVELLER in m.roles:
            if not TRAVELLER_ID_RE.match(m.traveller_id or ""):
                errors.append(f"{who}: a traveller login needs a traveller id like TR-1001")
        elif m.traveller_id:
            errors.append(f"{who}: only a traveller login is linked to a traveller id")
        if Role.CREW not in m.roles and CREW_NAME_RE.search(m.name):
            errors.append(f"{who}: {m.name!r} is written like a crew member's name")
    return errors
