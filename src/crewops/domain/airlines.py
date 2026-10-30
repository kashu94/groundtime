"""The airlines flying the network.

Three fictional Indian airlines, each with its own aircraft, flight numbers (airline code
plus three digits) and crew.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crewops.domain.models import DataError, _list, _str

AIRLINE_CODE_RE = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True, slots=True)
class Airline:
    code: str
    name: str
    aircraft: tuple[str, ...]
    color: str

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], ctx: str = "airline") -> Airline:
        code = _str(d, "code", ctx)
        if not AIRLINE_CODE_RE.match(code):
            raise DataError(f"{ctx}.code: two capital letters, got {code!r}")
        color = _str(d, "color", ctx)
        if not re.match(r"^#[0-9a-fA-F]{6}$", color):
            raise DataError(f"{ctx}.color: a #rrggbb colour, got {color!r}")
        return cls(
            code=code,
            name=_str(d, "name", ctx),
            aircraft=tuple(str(a) for a in _list(d, "aircraft", ctx)),
            color=color,
        )


__all__ = ["AIRLINE_CODE_RE", "Airline"]
