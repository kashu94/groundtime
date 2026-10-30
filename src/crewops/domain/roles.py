"""Who signs in to Groundtime, and what each role is for.

Roles are Cognito groups, which only an admin changes. Every permission is checked in the
MCP server from the caller's verified roles, never from what they type.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    TRAVELLER = "traveller"
    """A passenger: books a trip, shares what they love, and gets a plan when they wait."""
    CREW = "crew"
    """Flies the network: their own flights, and a plan for each layover."""
    CUSTOMER_CARE = "customer_care"
    """Records delays as operations confirm them, and looks after every waiting passenger."""
    ADMIN = "admin"
    """Looks after the accounts."""


@dataclass(frozen=True, slots=True)
class Caller:
    """Who is asking, as verified at sign-in. Never taken from what they type."""

    user_id: str
    roles: frozenset[Role]
    crew_id: str | None = None
    """Their own crew record, when they are crew."""
    traveller_id: str | None = None
    """Their own passenger record (``TR-...``), when they are a traveller."""
