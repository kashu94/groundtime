"""Who a disruption's status change is waiting on, and how urgent it is.

Desktop alerts use this to pick their people:

* analysed (REPORTED -> OPTIONS_READY) or sent back (SUBMITTED -> OPTIONS_READY) goes to the
  controller of the assigned desk
* plan submitted (OPTIONS_READY -> SUBMITTED) or a resolution to sign off goes to every
  approver

Planned leave goes to nobody: it is re-crewed weeks ahead and nothing about it is urgent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crewops.notify.changes import change_of


def desk_of(record: dict[str, Any]) -> str | None:
    from boto3.dynamodb.types import TypeDeserializer

    image = (record.get("dynamodb") or {}).get("NewImage") or {}
    analysis = image.get("analysis")
    if not analysis:
        return None
    value = TypeDeserializer().deserialize(analysis)
    return value.get("desk") if isinstance(value, dict) else None


def recipients(record: dict[str, Any], people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The people (each with ``username``, ``roles``, ``desk`` and ``notifications``) this
    change is for."""
    change = change_of(record)
    if change is None or change.report_type == "planned_leave":
        return []
    allowed = [p for p in people if p.get("notifications") and p.get("username")]
    if change.after in ("SUBMITTED", "RESOLVING"):
        return [p for p in allowed if "approver" in (p.get("roles") or [])]
    if change.after == "OPTIONS_READY" and change.before in ("REPORTED", "SUBMITTED", "RESOLVING"):
        desk = desk_of(record)
        return [
            p
            for p in allowed
            if desk and "controller" in (p.get("roles") or []) and p.get("desk") == desk
        ]
    return []


def rated(record: dict[str, Any]) -> str | None:
    """Severity level (high/medium/low), or None if the record has no usable analysis."""
    from boto3.dynamodb.types import TypeDeserializer

    from crewops.analysis.severity import severity

    image = (record.get("dynamodb") or {}).get("NewImage") or {}
    try:
        analysis = TypeDeserializer().deserialize(image["analysis"])
        report = TypeDeserializer().deserialize(image["report"])
        today = datetime.now(UTC).date()
        return severity(analysis, str(report.get("reported_utc") or ""), today)["level"]
    except Exception:
        return None


def current(people: list[dict[str, Any]], profile: Any) -> list[dict[str, Any]]:
    """Refresh roles and desk from the profile, since a subscription only has what they were
    when the browser subscribed. People who left the team are dropped."""
    out = []
    for person in people:
        found = profile(person.get("username") or "")
        if not found:
            continue
        out.append(person | {"roles": list(found.get("roles") or []), "desk": found.get("desk")})
    return out
