"""Bookings and delays.

    BOOKING / TR-id      flight_ids, position, username, name, booked_utc
    DELAY / flight-id    delay_minutes, reason, recorded_by, recorded_utc, times, history

A traveller has one booking at a time: booking again replaces it. A delay is recorded by
customer care as operations confirm it, and revised or cleared the same way. The latest word
on a flight is what plans use; ``history`` keeps every change with who made it and when, and
``times`` counts the delays recorded, so a flight can be marked late only so many times.
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


class TooManyDelays(Exception):
    """The flight has already been marked late as many times as allowed."""


def record_delay(
    table: Any,
    flight_id: str,
    minutes: int,
    reason: str,
    by: str,
    at: datetime,
    *,
    max_times: int,
) -> dict[str, Any]:
    """Set the flight's delay, or clear it with 0. A delay (not a clear) counts towards
    ``max_times``; the check and the write are one conditional update, so two people saving
    at once can't get past it."""
    from botocore.exceptions import ClientError

    change = {"minutes": minutes, "reason": reason, "by": by, "at": _iso(at)}
    names = {
        "#m": "delay_minutes",
        "#r": "reason",
        "#b": "recorded_by",
        "#a": "recorded_utc",
        "#h": "history",
        "#t": "times",
        "#f": "flight_id",
        "#e": "entity",
    }
    values: dict[str, Any] = {
        ":m": minutes,
        ":r": reason,
        ":b": by,
        ":a": _iso(at),
        ":h": [change],
        ":none": [],
        ":f": flight_id,
        ":e": "delay",
        ":zero": 0,
    }
    update = (
        "SET #m = :m, #r = :r, #b = :b, #a = :a, #f = :f, #e = :e, "
        "#h = list_append(if_not_exists(#h, :none), :h)"
    )
    kwargs: dict[str, Any] = {}
    if minutes > 0:
        update += ", #t = if_not_exists(#t, :zero) + :one"
        values |= {":one": 1, ":max": max_times}
        kwargs["ConditionExpression"] = "attribute_not_exists(#t) OR #t < :max"
    else:
        update += ", #t = if_not_exists(#t, :zero)"
    try:
        out = table.update_item(
            Key={schema.PK: DELAYS_PK, schema.SK: flight_id},
            UpdateExpression=update,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
            **kwargs,
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise TooManyDelays(flight_id) from None
        raise
    return _strip(from_dynamo(out["Attributes"]))


def delay_of(table: Any, flight_id: str) -> dict[str, Any] | None:
    item = table.get_item(
        Key={schema.PK: DELAYS_PK, schema.SK: flight_id}, ConsistentRead=True
    ).get("Item")
    return None if item is None else _strip(from_dynamo(item))


def all_delays(table: Any) -> dict[str, dict[str, Any]]:
    """Flight id -> what was recorded on it, cleared delays (0 minutes) included."""
    return {i["flight_id"]: _strip(i) for i in _all(table, DELAYS_PK)}
