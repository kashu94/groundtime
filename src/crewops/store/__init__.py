"""DynamoDB access: the one table and the items in it."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any


def table_for(settings: Any, session: Any = None) -> Any:
    """The stage's table, as a boto3 resource."""
    import boto3

    session = session or boto3.Session(region_name=settings.aws_region)
    return session.resource("dynamodb").Table(settings.table_name)


def from_dynamo(value: Any) -> Any:
    """Undo boto3's ``Decimal`` so items read back exactly as they were written."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, Mapping):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [from_dynamo(v) for v in value]
    if isinstance(value, set):
        return sorted(from_dynamo(v) for v in value)
    return value
