"""Bookings and delays.

    BOOKING / TR-id      flight_ids, position, username, name, booked_utc
    DELAY / flight-id    delay_minutes, reason, recorded_by, recorded_utc

A traveller has one booking at a time: booking again replaces it. A delay is recorded by
customer care as operations confirm it, and replaced or cleared the same way; the latest
word on a flight is the only one kept.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from crewops.store import from_dynamo, schema

BOOKINGS_PK = "BOOKING"
DELAYS_PK = "DELAY"


def _iso(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def _all(table: Any, pk: str) -> list[dict[str, Any]]:
    from boto3.dynamodb.conditions import Key

    out: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {"KeyConditionExpression": Key(schema.PK).eq(pk)}
    while True:
        page = table.query(**kwargs)
        out += [from_dynamo(i) for i in page.get("Items", [])]
        if "LastEvaluatedKey" not in page:
            return out
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def _strip(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in (schema.PK, schema.SK, "entity")}


# -- Bookings -------------------------------------------------------------------


def save_booking(
    table: Any,
    traveller_id: str,
    *,
    username: str,
    name: str,
    flight_ids: Iterable[str],
    position: str,
    at: datetime,
) -> dict[str, Any]:
    item = {
        schema.PK: BOOKINGS_PK,
        schema.SK: traveller_id,
        "entity": "booking",
        "traveller_id": traveller_id,
        "username": username,
        "name": name,
        "flight_ids": list(flight_ids),
        "position": position,
        "booked_utc": _iso(at),
    }
    table.put_item(Item=item)
    return _strip(item)


def set_position(table: Any, traveller_id: str, position: str) -> None:
    table.update_item(
        Key={schema.PK: BOOKINGS_PK, schema.SK: traveller_id},
        UpdateExpression="SET #p = :p",
        ConditionExpression="attribute_exists(#pk)",
        ExpressionAttributeNames={"#p": "position", "#pk": schema.PK},
        ExpressionAttributeValues={":p": position},
    )


def booking_of(table: Any, traveller_id: str) -> dict[str, Any] | None:
    item = table.get_item(
        Key={schema.PK: BOOKINGS_PK, schema.SK: traveller_id}, ConsistentRead=True
    ).get("Item")
    return None if item is None else _strip(from_dynamo(item))


def all_bookings(table: Any) -> list[dict[str, Any]]:
    return [_strip(i) for i in _all(table, BOOKINGS_PK)]


def delete_booking(table: Any, traveller_id: str) -> None:
    table.delete_item(Key={schema.PK: BOOKINGS_PK, schema.SK: traveller_id})


# -- Delays ---------------------------------------------------------------------


def record_delay(
    table: Any, flight_id: str, minutes: int, reason: str, by: str, at: datetime
) -> dict[str, Any]:
    item = {
        schema.PK: DELAYS_PK,
        schema.SK: flight_id,
        "entity": "delay",
        "flight_id": flight_id,
        "delay_minutes": minutes,
        "reason": reason,
        "recorded_by": by,
        "recorded_utc": _iso(at),
    }
    table.put_item(Item=item)
    return _strip(item)


def clear_delay(table: Any, flight_id: str) -> None:
    table.delete_item(Key={schema.PK: DELAYS_PK, schema.SK: flight_id})


def all_delays(table: Any) -> dict[str, dict[str, Any]]:
    """Flight id -> the delay recorded on it."""
    return {i["flight_id"]: _strip(i) for i in _all(table, DELAYS_PK)}
