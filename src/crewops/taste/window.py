"""The free time a crew really has on a layover, from the crew trip alone.

Rest runs from release to the next report, at least 12 hours. Little of it is free: the
crew ride to the hotel and check in, and must be asleep early enough for a full sleep before
the ride back and the report. What is left is when a meal out fits, if it fits at all. A
long duty day, or a short window, makes the brief favour somewhere quiet and close.

All of it is arithmetic on trip times; Qloo only ever sees the place and the hour.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from crewops.taste.stations import CrewHotel

CHECK_IN = timedelta(minutes=30)
"""Hotel check-in and changing out of uniform."""
SLEEP = timedelta(hours=8)
"""Sleep opportunity protected before the next report."""
BEFORE_REPORT = timedelta(minutes=60)
"""Waking, breakfast and getting ready, before the ride back."""
MEAL = timedelta(minutes=75)
"""Time a sit-down meal needs, door to door."""
DINNER_FROM = 19
"""Local hour before which an early arrival is pointed at dinner rather than a snack."""
LONG_DAY_HOURS = 10.0
"""A flight duty period this long or longer counts as a tiring day."""


@dataclass(frozen=True, slots=True)
class LayoverWindow:
    hotel: CrewHotel
    release_utc: datetime
    next_report_utc: datetime
    duty_hours: float | None
    min_rest_hours: float
    free_from: datetime
    """Local time the crew can leave the hotel."""
    sleep_by: datetime
    """Local time they need to be back and asleep."""
    meal_at: datetime | None
    """Local time to book for, or None when there is no time for a meal out."""

    @property
    def rest_hours(self) -> float:
        return round((self.next_report_utc - self.release_utc).total_seconds() / 3600, 2)

    @property
    def legal_rest(self) -> bool:
        return self.rest_hours >= self.min_rest_hours

    @property
    def free_minutes(self) -> int:
        return max(0, int((self.sleep_by - self.free_from).total_seconds() // 60))

    @property
    def tiring(self) -> bool:
        """Favour somewhere quiet and close: a long day, or barely time for a meal."""
        long_day = self.duty_hours is not None and self.duty_hours >= LONG_DAY_HOURS
        return long_day or self.free_minutes < 2 * MEAL.total_seconds() / 60

    def to_dict(self) -> dict[str, Any]:
        def local(t: datetime | None) -> str | None:
            return None if t is None else t.strftime("%Y-%m-%d %H:%M")

        return {
            "station": self.hotel.station,
            "city": self.hotel.city,
            "hotel_area": self.hotel.area,
            "release_utc": self.release_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "next_report_utc": self.next_report_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rest_hours": self.rest_hours,
            "legal_rest": self.legal_rest,
            "duty_hours": self.duty_hours,
            "free_from_local": local(self.free_from),
            "sleep_by_local": local(self.sleep_by),
            "free_minutes": self.free_minutes,
            "meal_at_local": local(self.meal_at),
            "tiring": self.tiring,
            "timezone": self.hotel.tz.tzname(None),
        }


def layover_window(
    hotel: CrewHotel,
    release_utc: datetime,
    next_report_utc: datetime,
    *,
    min_rest_hours: float,
    duty_hours: float | None = None,
) -> LayoverWindow:
    transfer = timedelta(minutes=hotel.transfer_minutes)
    free_from = (release_utc + transfer + CHECK_IN).astimezone(hotel.tz)
    sleep_by = (next_report_utc - transfer - BEFORE_REPORT - SLEEP).astimezone(hotel.tz)
    meal_at: datetime | None = None
    if sleep_by - free_from >= MEAL:
        dinner = free_from.replace(hour=DINNER_FROM, minute=0, second=0, microsecond=0)
        meal_at = dinner if free_from < dinner and dinner + MEAL <= sleep_by else free_from
        meal_at = _round_up(meal_at)
        if meal_at + MEAL > sleep_by:
            meal_at = free_from
    return LayoverWindow(
        hotel=hotel,
        release_utc=release_utc,
        next_report_utc=next_report_utc,
        duty_hours=duty_hours,
        min_rest_hours=min_rest_hours,
        free_from=free_from,
        sleep_by=sleep_by,
        meal_at=meal_at,
    )


def _round_up(t: datetime) -> datetime:
    """To the next quarter hour, the way a table is booked."""
    extra = (-t.minute) % 15
    return (t + timedelta(minutes=extra)).replace(second=0, microsecond=0)
