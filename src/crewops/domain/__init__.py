"""Typed records shared by every layer: the network, the store, the server."""

from crewops.domain.airlines import Airline
from crewops.domain.models import (
    AircraftType,
    Crew,
    CrewStatus,
    DataError,
    Flight,
    Pairing,
    PairingDay,
    PairingSeat,
    Rank,
    parse_date,
    parse_utc,
)
from crewops.domain.roles import Caller, Role

__all__ = [
    "AircraftType",
    "Airline",
    "Caller",
    "Crew",
    "CrewStatus",
    "DataError",
    "Flight",
    "Pairing",
    "PairingDay",
    "PairingSeat",
    "Rank",
    "Role",
    "parse_date",
    "parse_utc",
]
