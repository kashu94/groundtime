import json
import urllib.parse
from datetime import UTC, date, datetime

import pytest

from crewops.ingestion.seed import load_seed
from crewops.network import build_network
from crewops.store.taste import TableCache, profile_of, profiles_of, save_profile
from crewops.taste.layover import NightStop, layover_brief, night_stops
from crewops.taste.profile import ProfileError, TasteProfile
from crewops.taste.qloo import QlooClient
from crewops.taste.stations import CREW_HOTELS, hotel_at
from crewops.taste.venues import venue_from_entity
from crewops.taste.window import layover_window

RAHMAN = "9986F595-C20E-4EBB-828F-55E7DEEBE448"
LAGAAN = "3A923B32-FCEA-4060-8609-8895309F7B80"
LATE = {"opens": "T12:00:00", "closes": "T01:00:00", "closed": False}
EARLY = {"opens": "T08:00:00", "closes": "T21:30:00", "closed": False}
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def place(
    n,
    name,
    *,
    hours=LATE,
    dietary=(),
    noise="moderate",
    distance=400,
    affinity=0.8,
    genres=("Restaurant",),
):
    tags = [
        {"id": f"urn:tag:dietary_option:qloo:{d}", "type": "urn:tag:dietary_option:qloo"}
        for d in dietary
    ]
    tags.append({"id": f"urn:tag:noise_level:qloo:{noise}", "type": "urn:tag:noise_level:qloo"})
    tags += [
        {"id": f"urn:tag:genre:place:{g.lower()}", "name": g, "type": "urn:tag:genre:place"}
        for g in genres
    ]
    return {
        "entity_id": f"00000000-0000-0000-0000-{n:012d}",
        "name": name,
        "properties": {
            "address": "Aerocity, New Delhi",
            "hours": None if hours is None else {d: [hours] for d in DAYS},
            "business_rating": 4.2,
        },
        "location": {"lat": 28.55, "lon": 77.12},
        "query": {"distance": distance, "affinity": affinity},
        "tags": tags,
    }


AEROCITY = [
    place(1, "Late Kitchen", dietary=("vegetarian", "jain"), affinity=0.91),
    place(2, "Closes Early", hours=EARLY, dietary=("vegetarian", "jain"), affinity=0.95),
    place(3, "Loud Bar", dietary=("vegetarian", "jain"), noise="loud", affinity=0.97),
    place(4, "No Veg Grill", dietary=(), affinity=0.99),
    place(5, "Terminal Food Court", dietary=("vegetarian", "jain"), genres=("Food court",)),
    place(6, "Quiet Thali", dietary=("vegetarian", "jain"), noise="quiet", affinity=0.85),
    place(7, "Far Away", dietary=("vegetarian", "jain"), distance=9000),
]


class FakeQloo:
    def __init__(self, entities):
        self.entities = entities
        self.queries = []

    def __call__(self, url, headers, timeout):
        self.queries.append(urllib.parse.parse_qs(urllib.parse.urlparse(url).query))
        return 200, json.dumps({"results": {"entities": self.entities}}).encode(), {}


@pytest.fixture(scope="module")
def world():
    return build_network(load_seed())


def qloo(fake):
    return QlooClient("https://qloo.example", lambda: "k", transport=fake)


def profile(crew_id, **d):
    return TasteProfile.from_dict(crew_id, d)


def test_the_seed_week_has_its_delhi_night_stops(world):
    stops = night_stops(world, pairing_id="P-2291")
    assert [(s.station, s.date) for s in stops] == [("DEL", date(2026, 10, 13))]
    stop = stops[0]
    assert stop.release_utc == datetime(2026, 10, 13, 15, 30, tzinfo=UTC)
    assert stop.next_report_utc == datetime(2026, 10, 14, 4, 0, tzinfo=UTC)
    assert len(stop.crew_ids) >= 4
    crew = stop.crew_ids[0]
    assert night_stops(world, crew_id=crew, on=date(2026, 10, 13))[0].pairing_id == "P-2291"


def test_every_station_has_a_crew_hotel(world):
    stations = {f.arr_station for f in world.flights.values()}
    assert stations <= set(CREW_HOTELS)
    assert hotel_at("del").point == "POINT(77.121 28.5503)"


def test_the_window_protects_sleep_before_the_next_report():
    # Released at DEL 21:00 IST, reporting 09:30 IST: ride, check in, then 8 h sleep, an
    # hour to get ready and the ride back leave 21:45 to 00:15 free.
    w = layover_window(
        hotel_at("DEL"),
        datetime(2026, 10, 13, 15, 30, tzinfo=UTC),
        datetime(2026, 10, 14, 4, 0, tzinfo=UTC),
        min_rest_hours=12,
        duty_hours=8.5,
    )
    assert f"{w.free_from:%H:%M}" == "21:45" and f"{w.sleep_by:%H:%M}" == "00:15"
    assert f"{w.meal_at:%H:%M}" == "21:45" and w.free_minutes == 150
    assert w.legal_rest and w.rest_hours == 12.5
    assert not w.tiring


def test_an_early_release_books_dinner_not_a_late_lunch():
    w = layover_window(
        hotel_at("DEL"),
        datetime(2026, 10, 13, 8, 0, tzinfo=UTC),  # 13:30 IST
        datetime(2026, 10, 14, 4, 0, tzinfo=UTC),
        min_rest_hours=12,
    )
    assert f"{w.meal_at:%H:%M}" == "19:00"


def test_no_time_for_a_meal_means_rest_first_and_no_qloo_call():
    fake = FakeQloo(AEROCITY)
    stop = NightStop(
        "P-X",
        date(2026, 10, 13),
        "DEL",
        datetime(2026, 10, 13, 18, 30, tzinfo=UTC),
        datetime(2026, 10, 14, 4, 0, tzinfo=UTC),
        ("C-1",),
    )
    brief = layover_brief(stop, {}, qloo(fake), min_rest_hours=12)
    assert brief.picks == () and "rest comes first" in brief.note
    assert fake.queries == []
    assert not brief.window.legal_rest


def test_the_brief_keeps_only_places_that_suit_the_whole_crew_tonight(world):
    stop = night_stops(world, pairing_id="P-2291")[0]
    a, b, c = stop.crew_ids[:3]
    profiles = {
        a: profile(
            a,
            loves=[{"id": RAHMAN, "name": "A. R. Rahman", "type": "urn:entity:artist"}],
            dietary=["vegetarian"],
            wind_down="quiet",
        ),
        b: profile(
            b,
            loves=[
                {"id": LAGAAN, "name": "Lagaan", "type": "urn:entity:movie"},
                {"id": RAHMAN, "name": "A. R. Rahman", "type": "urn:entity:artist"},
            ],
            dietary=["jain"],
        ),
        c: profile(c, wind_down="quiet"),
        "C-9999": profile("C-9999", dietary=["halal"]),  # not on this trip
    }
    fake = FakeQloo(AEROCITY)
    brief = layover_brief(stop, profiles, qloo(fake), min_rest_hours=12)
    names = [p.venue.name for p in brief.picks]
    assert names == ["Quiet Thali", "Late Kitchen"]
    assert brief.dietary_needed == {"vegetarian", "jain"}
    assert brief.quiet and brief.taste_shared_by == 2
    assert brief.rejected == {
        "closed at 21:45 or too soon after": 1,
        "loud": 1,
        "missing a dietary option the crew needs": 1,
        "airside or food court": 1,
        "too far": 1,
    }
    why = brief.picks[0].why
    assert why[0] == "Open at 21:45, until 01:00"
    assert "Offers Jain, vegetarian food" in why and "Quiet, for a tired crew" in why
    # The shared pick goes first among the signals, and Qloo hears ids, never people.
    main = fake.queries[0]
    assert main["signal.interests.entities"] == [f"{RAHMAN},{LAGAAN}"]
    assert main["filter.location"] == ["POINT(77.121 28.5503)"]
    assert fake.queries[1]["filter.tags"] == ["urn:tag:dietary_option:qloo:jain"]
    sent = json.dumps(fake.queries)
    assert not any(crew in sent for crew in stop.crew_ids)
    # The staff view hides whose diet is whose; the crew member's own view shows it.
    assert "dietary_needed" not in brief.to_dict()
    assert brief.to_dict()["dietary_needs_met"] is True
    assert brief.to_dict(for_crew=True)["dietary_needed"] == ["jain", "vegetarian"]


def test_unknown_hours_rank_below_listed_hours_and_say_so():
    v = venue_from_entity(place(9, "No Hours", hours=None))
    assert v.hours is None and v.open_through(datetime(2026, 10, 13, 22, 0), 60) is None
    fake = FakeQloo([place(9, "No Hours", hours=None, affinity=0.99), place(1, "Late Kitchen")])
    stop = NightStop(
        "P-X",
        date(2026, 10, 13),
        "DEL",
        datetime(2026, 10, 13, 15, 30, tzinfo=UTC),
        datetime(2026, 10, 14, 4, 0, tzinfo=UTC),
        ("C-1",),
    )
    brief = layover_brief(stop, {}, qloo(fake), min_rest_hours=12)
    assert [p.venue.name for p in brief.picks] == ["Late Kitchen", "No Hours"]
    assert brief.picks[1].why[-1] == "Opening hours not listed: call ahead"


def test_a_span_past_midnight_counts_on_the_next_day():
    v = venue_from_entity(place(1, "Late Kitchen"))
    assert v.open_through(datetime(2026, 10, 14, 0, 15), 30)  # Wednesday, from Tuesday night
    assert not v.open_through(datetime(2026, 10, 14, 0, 30), 45)


@pytest.mark.parametrize(
    ("d", "error"),
    [
        ({"loves": [{"id": "not-an-id", "name": "x", "type": "urn:entity:artist"}]}, "Qloo id"),
        ({"loves": [{"id": RAHMAN, "name": "x", "type": "urn:entity:car"}]}, "unknown type"),
        ({"loves": [{"id": RAHMAN, "name": "x", "type": "urn:entity:artist"}] * 6}, "at most 5"),
        ({"dietary": ["paleo"]}, "dietary"),
        ({"wind_down": "party"}, "quiet or lively"),
    ],
)
def test_a_profile_takes_only_qloo_picks_and_known_needs(d, error):
    with pytest.raises(ProfileError, match=error):
        TasteProfile.from_dict("C-1042", d)


def test_profiles_and_the_qloo_cache_live_in_the_table(ops_table):
    at = datetime(2026, 10, 12, 18, 0, tzinfo=UTC)
    saved = save_profile(
        ops_table,
        profile(
            "C-1042",
            loves=[{"id": RAHMAN, "name": "A. R. Rahman", "type": "urn:entity:artist"}],
            dietary=["jain"],
        ),
        at,
    )
    assert saved.updated_utc == "2026-10-12T18:00:00Z"
    assert profile_of(ops_table, "C-1042") == saved
    save_profile(ops_table, profile("C-2087", wind_down="lively"), at)
    assert set(profiles_of(ops_table, ["C-1042", "C-2087", "C-0000"])) == {"C-1042", "C-2087"}

    now = [1000.0]
    cache = TableCache(ops_table, clock=lambda: now[0])
    cache.put("k", {"results": {"entities": AEROCITY}}, 60)
    assert cache.get("k")["results"]["entities"][0]["name"] == "Late Kitchen"
    now[0] = 1061.0
    assert cache.get("k") is None


def test_a_delay_on_the_last_leg_moves_the_evening(world):
    stop = night_stops(world, pairing_id="P-2291")[0]
    last = world.pairings["P-2291"].days[0].flight_ids[-1]
    late = night_stops(world, pairing_id="P-2291", delays={last: 90})[0]
    assert (late.release_utc - stop.release_utc).total_seconds() == 90 * 60
    assert late.cause == "delay" and late.duty_hours == stop.duty_hours + 1.5
