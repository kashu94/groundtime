"""Where crews stay at each station, where passengers wait, and how far either will go.

One crew hotel area per station: the point layover searches start from, the time the hotel
transfer takes each way, and the local clock. One terminal per station for passengers, with
the times a passenger must allow to get through it. Every station in the network is in
India, so local time is IST (UTC+05:30, no daylight saving) and no time zone database is
needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


@dataclass(frozen=True, slots=True)
class CrewHotel:
    station: str
    city: str
    area: str
    lat: float
    lon: float
    transfer_minutes: int
    """Airport to hotel, and back for the next report."""
    radius_m: int = 3000
    """How far a crew will walk or take a short ride for a meal."""
    tz: timezone = IST

    @property
    def point(self) -> str:
        """WKT, the way Qloo's ``filter.location`` takes it: longitude first."""
        return f"POINT({self.lon} {self.lat})"


CREW_HOTELS: dict[str, CrewHotel] = {
    h.station: h
    for h in (
        CrewHotel("BLR", "Bengaluru", "Hebbal", 13.0358, 77.5970, 45),
        CrewHotel("BOM", "Mumbai", "Andheri East", 19.1136, 72.8697, 20),
        CrewHotel("CCU", "Kolkata", "New Town", 22.5867, 88.4171, 25),
        CrewHotel("COK", "Kochi", "Nedumbassery", 10.1518, 76.3930, 15, radius_m=5000),
        CrewHotel("DEL", "New Delhi", "Aerocity", 28.5503, 77.1210, 15),
        CrewHotel("GOI", "Goa", "Vasco da Gama", 15.3960, 73.8150, 20, radius_m=4000),
        CrewHotel("HYD", "Hyderabad", "HITEC City", 17.4435, 78.3772, 45),
        CrewHotel("MAA", "Chennai", "Guindy", 13.0108, 80.2120, 20),
    )
}


def hotel_at(station: str) -> CrewHotel | None:
    return CREW_HOTELS.get(station.upper())


@dataclass(frozen=True, slots=True)
class Airport:
    """The domestic terminal at a station, and the times a passenger has to allow there.

    Every flight in the network is domestic, so no visa or immigration applies. What decides
    whether a passenger can go anywhere is whether they have reached the airport: Indian
    airports let a passenger back out of the departure terminal only with the airline's and
    security's clearance, so a plan for someone already there stays inside.
    """

    station: str
    city: str
    name: str
    lat: float
    lon: float
    city_radius_m: int = 12000
    """How far from the airport an outing on the way in may go."""
    security_minutes: int = 45
    """Bag drop and security, from the terminal door to airside."""
    gate_close_minutes: int = 25
    """Boarding gate closes this long before departure."""
    tz: timezone = IST

    @property
    def point(self) -> str:
        return f"POINT({self.lon} {self.lat})"


AIRPORTS: dict[str, Airport] = {
    a.station: a
    for a in (
        Airport("BLR", "Bengaluru", "Kempegowda International, Terminal 1", 13.1989, 77.7069),
        Airport("BOM", "Mumbai", "Chhatrapati Shivaji Maharaj International, T2", 19.0989, 72.8740),
        Airport("CCU", "Kolkata", "Netaji Subhas Chandra Bose International", 22.6533, 88.4467),
        Airport("COK", "Kochi", "Cochin International, Terminal 1", 10.1556, 76.3913),
        Airport("DEL", "New Delhi", "Indira Gandhi International, Terminal 1", 28.5652, 77.1196),
        Airport("GOI", "Goa", "Dabolim", 15.3808, 73.8314, city_radius_m=15000),
        Airport("HYD", "Hyderabad", "Rajiv Gandhi International", 17.2403, 78.4294),
        Airport("MAA", "Chennai", "Chennai International, Terminal 1", 12.9814, 80.1638),
    )
}


def airport_at(station: str) -> Airport | None:
    return AIRPORTS.get(station.upper())
