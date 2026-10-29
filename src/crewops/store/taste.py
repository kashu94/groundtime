"""Crew and traveller taste profiles, and the Qloo answer cache.

    CREW#id / TASTE            loves, dietary, wind_down, updated_utc
    TRAVELLER#id / TASTE       the same, for a passenger (ids TR-...)
    QLOO / <request hash>      body (zlib JSON), expires_at

A profile is written only by its crew member, through the server. The cache holds Qloo's
answers for a day so the same night stop, asked about by the crew and the controller, costs
one Qloo call; DynamoDB deletes each entry when it expires.
"""

from __future__ import annotations

import json
import time
import zlib
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from crewops.store import schema
from crewops.store.items import from_dynamo
from crewops.store.schema import SEPARATOR as S
from crewops.taste.profile import TasteProfile

ENTITY = "taste_profile"
CACHE_PK = "QLOO"
MAX_CACHED_BYTES = 350_000
"""DynamoDB items stop at 400 KB. A larger answer is simply not cached."""


def _key(owner_id: str) -> dict[str, str]:
    """A crew member's profile, or a traveller's (``TR-...``)."""
    kind = "TRAVELLER" if owner_id.startswith("TR-") else "CREW"
    return {schema.PK: f"{kind}{S}{owner_id}", schema.SK: "TASTE"}


def save_profile(table: Any, profile: TasteProfile, at: datetime) -> TasteProfile:
    stamped = TasteProfile(
        crew_id=profile.crew_id,
        loves=profile.loves,
        dietary=profile.dietary,
        wind_down=profile.wind_down,
        updated_utc=at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    body = stamped.to_dict()
    item: dict[str, Any] = {**_key(profile.crew_id), "entity": ENTITY, **body}
    if not body["dietary"]:
        del item["dietary"]  # DynamoDB has no empty sets; an empty list is fine but pointless
    table.put_item(Item={k: v for k, v in item.items() if v is not None})
    return stamped


def delete_profile(table: Any, crew_id: str) -> None:
    table.delete_item(Key=_key(crew_id))


def profile_of(table: Any, crew_id: str) -> TasteProfile | None:
    item = table.get_item(Key=_key(crew_id), ConsistentRead=True).get("Item")
    return None if item is None else TasteProfile.from_dict(crew_id, from_dynamo(item))


def profiles_of(table: Any, crew_ids: Iterable[str]) -> dict[str, TasteProfile]:
    """Profiles of whichever of ``crew_ids`` have one."""
    ids = sorted(set(crew_ids))
    out: dict[str, TasteProfile] = {}
    client = table.meta.client
    for start in range(0, len(ids), 100):
        keys: list[dict[str, str]] | None = [_key(c) for c in ids[start : start + 100]]
        while keys:
            page = client.batch_get_item(RequestItems={table.name: {"Keys": keys}})
            for item in page.get("Responses", {}).get(table.name, []):
                crew_id = str(item[schema.PK]).split(S, 1)[1]
                out[crew_id] = TasteProfile.from_dict(crew_id, from_dynamo(item))
            keys = page.get("UnprocessedKeys", {}).get(table.name, {}).get("Keys")
    return out


class TableCache:
    """``crewops.taste.qloo.Cache`` over the operations table."""

    def __init__(self, table: Any, clock: Any = time.time) -> None:
        self._table = table
        self._clock = clock

    def get(self, key: str) -> Any | None:
        item = self._table.get_item(Key={schema.PK: CACHE_PK, schema.SK: key}).get("Item")
        if item is None or int(item.get(schema.TTL, 0)) < self._clock():
            return None  # TTL deletion runs late, so expiry is checked here too
        return json.loads(zlib.decompress(bytes(item["body"].value)))

    def put(self, key: str, value: Any, ttl_seconds: int) -> None:
        body = zlib.compress(json.dumps(value, separators=(",", ":")).encode(), 6)
        if len(body) > MAX_CACHED_BYTES:
            return
        self._table.put_item(
            Item={
                schema.PK: CACHE_PK,
                schema.SK: key,
                "entity": "qloo_cache",
                "body": body,
                schema.TTL: int(self._clock()) + ttl_seconds,
            }
        )
