import json
import urllib.parse
from datetime import UTC, datetime

import pytest

from crewops.domain import Caller, Role
from crewops.ingestion.seed import load_seed
from crewops.mcp.api import ApiError, GroundtimeApi
from crewops.network import build_network
from crewops.store import trips as trip_store
from crewops.taste.concierge import Concierge, grounded
from crewops.taste.groundtime import ground_wait, late_by, plan_groundtime, ride_minutes
from crewops.taste.profile import TasteProfile
from crewops.taste.qloo import QlooClient
from crewops.taste.service import Groundtime
from crewops.taste.travellers import Position, find_trips, load_travellers, trip

RAHMAN = "9986F595-C20E-4EBB-828F-55E7DEEBE448"
NOW = datetime(2026, 10, 13, 7, 30, tzinfo=UTC)  # 13:00 IST
KS434 = "KS434-2026-10-13"  # Goa to Bengaluru, 16:00 IST
ALL_DAY = {"opens": "T09:00:00", "closes": "T23:00:00", "closed": False}
MORNING = {"opens": "T09:00:00", "closes": "T12:00:00", "closed": False}
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def place(n, name, genres, *, lat, lon, dietary=(), hours=ALL_DAY, distance=4000, affinity=0.8):
    tags = [
        {"id": f"urn:tag:genre:place:{g}", "name": g, "type": "urn:tag:genre:place"} for g in genres
    ]
    tags += [{"id": f"urn:tag:dietary_option:qloo:{d}", "type": "x"} for d in dietary]
    return {
        "entity_id": f"00000000-0000-0000-0000-{n:012d}",
        "name": name,
        "properties": {"hours": None if hours is None else {d: [hours] for d in DAYS}},
        "location": {"lat": lat, "lon": lon},
        "query": {"distance": distance, "affinity": affinity},
        "tags": tags,
    }


GOA = [
    place(1, "Fort Walk", ["Fortress", "Tourist attraction"], lat=15.40, lon=73.84, affinity=0.9),
    place(2, "Seaside Hotel", ["Hotel", "Tourist attraction"], lat=15.39, lon=73.83, affinity=0.99),
    place(3, "Far Beach", ["Beach"], lat=15.60, lon=73.74, distance=16000),
    place(4, "Veg Thali", ["Restaurant"], lat=15.39, lon=73.84, dietary=("vegetarian",)),
    place(5, "Fish Shack", ["Restaurant"], lat=15.39, lon=73.84),
    place(6, "Shut Museum", ["Museum"], lat=15.39, lon=73.84, hours=MORNING),
]  # fmt: skip
TERMINAL = [
    place(7, "Gate Cafe", ["Cafe"], lat=15.381, lon=73.831, distance=100, dietary=("vegetarian",)),
    place(8, "Duty Free", ["Duty free store"], lat=15.381, lon=73.831, distance=80),
]
FILMS = [
    {"entity_id": "F1", "name": "Long Epic", "properties": {"duration": 240}},
    {"entity_id": "F2", "name": "Short Film", "properties": {"duration": 95}},
]  # fmt: skip


class FakeQloo:
    """Answers by what is asked for: films, series, places near the terminal, or the city."""

    def __init__(self):
        self.queries = []

    def __call__(self, url, headers, timeout):
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}
        self.queries.append(q)
        kind = q.get("filter.type")
        if kind == "urn:entity:movie":
            entities = FILMS
        elif kind == "urn:entity:tv_show":
            entities = [{"entity_id": "S1", "name": "Short Show", "properties": {"duration": 30}}]
        elif int(q.get("filter.location.radius", 0)) < 2000:
            entities = TERMINAL
        else:
            entities = GOA
        return 200, json.dumps({"results": {"entities": entities}}).encode(), {}


@pytest.fixture(scope="module")
def world():
    return build_network(load_seed())


def qloo(fake):
    return QlooClient("https://qloo.example", lambda: "k", transport=fake)


def taste(**d):
    return TasteProfile.from_dict("TR-1", d)


def legs(world, *nos):
    return trip(world.flights, nos, NOW)


RAHMAN_LOVE = {"id": RAHMAN, "name": "A. R. Rahman", "type": "urn:entity:artist"}


def test_the_network_repeats_the_seed_week_to_the_end_of_the_year(world):
    assert "KS434-2026-10-30" in world.flights and "KS434-2026-12-31" in world.flights
    later = world.flights["KS434-2026-10-27"]
    assert f"{later.dep_utc:%H:%M}" == f"{world.flights[KS434].dep_utc:%H:%M}"
    assert "P-2301" in world.pairings and world.airline_of("KS434")


def test_a_booking_resolves_to_the_day_the_flight_next_operates(world):
    assert [f.flight_id for f in legs(world, "KS434")] == [KS434]
    connection = legs(world, "KS432", "KS588")
    assert [f.flight_id for f in connection] == ["KS432-2026-10-13", "KS588-2026-10-13"]
    assert trip(world.flights, ("XX999",), NOW) == ()


def test_booking_search_offers_direct_flights_then_same_day_connections(world):
    direct = find_trips(world.flights, "GOI", "BLR", NOW.date(), NOW)
    assert direct and all(len(t.legs) == 1 for t in direct[:1])
    assert direct[0].legs[0].flight_id == KS434
    onward = find_trips(world.flights, "BOM", "DEL", NOW.date(), NOW)
    via = [t for t in onward if len(t.legs) == 2]
    assert any(t.legs[1].flight_id == "KS588-2026-10-13" for t in via)
    assert all(60 <= t.connection_minutes <= 360 for t in via)
    assert find_trips(world.flights, "GOI", "GOI", NOW.date(), NOW) == []


def test_a_delay_hands_back_time_to_someone_who_hasnt_left_yet(world):
    on_time = ground_wait(legs(world, "KS434"), Position.AWAY, NOW)
    assert on_time.outside_minutes == 0 and on_time.mode == "terminal"
    assert on_time.headline == "No delay on KS434: be at the terminal by 14:20."
    late = ground_wait(legs(world, "KS434"), Position.AWAY, NOW, {KS434: 240})
    # 16:00 departure, 4 h late: gate closes 19:35, be there by 19:20, terminal door by 18:20.
    assert f"{late.at_gate_by:%H:%M}" == "19:20" and f"{late.at_terminal_by:%H:%M}" == "18:20"
    assert f"{late.free_from:%H:%M}" == "14:20" and late.outside_minutes == 240
    assert late.mode == "city" and late.can_leave and late.stay_reason is None
    assert late.headline == (
        "You haven't left for the airport yet. KS434 is 4 h late, so instead of being at the "
        "airport at 14:20, here's what to do near it on your way in, before you need to be at "
        "the terminal by 18:20."
    )


def test_anyone_already_at_the_airport_stays_in_however_long_the_wait(world):
    wait = ground_wait(legs(world, "KS434"), Position.AIRPORT, NOW, {KS434: 600})
    assert not wait.can_leave and wait.mode == "terminal"
    assert f"{wait.free_from:%H:%M}" == "13:00"  # there now: the time is theirs from now
    assert "clearance" in wait.stay_reason
    assert wait.headline.startswith("You're at Goa airport. KS434 is 10 h late")


def test_a_connection_is_airside_from_the_arrival(world):
    wait = ground_wait(legs(world, "KS432", "KS588"), Position.AWAY, NOW)
    assert wait.flight.flight_id == "KS588-2026-10-13" and wait.position is Position.AIRPORT
    assert wait.connecting_from.flight_id == "KS432-2026-10-13" and not wait.can_leave
    assert f"{wait.free_from:%H:%M}" == "13:30"  # landed 13:15 IST, plus getting off
    assert wait.headline.startswith("You're connecting at Bengaluru for KS588")


def test_delays_read_in_plain_words():
    assert [late_by(m) for m in (45, 60, 150, 240)] == ["45 min", "1 h", "2 h 30 min", "4 h"]


def test_the_plan_on_the_way_in_keeps_real_sights_open_meals_and_gets_there_in_time(world):
    fake = FakeQloo()
    wait = ground_wait(legs(world, "KS434"), Position.AWAY, NOW, {KS434: 240})
    plan = plan_groundtime(wait, taste(loves=[RAHMAN_LOVE], dietary=["vegetarian"]), qloo(fake))
    names = [(s.kind, s.venue.name) for s in plan.stops]
    # Both orders fit; the one at the terminal sooner wins.
    assert sorted(names) == [("meal", "Veg Thali"), ("sight", "Fort Walk")]
    assert plan.back_at_terminal <= wait.at_terminal_by
    assert plan.rejected["not a place to visit"] >= 1  # the hotel Qloo calls an attraction
    assert plan.rejected["too far"] >= 1
    assert plan.rejected["missing a dietary option you need"] >= 1
    first = plan.stops[0]
    assert first.arrive.minute % 5 == 0 and first.ride_minutes > ride_minutes(0)
    # The film plays on the flight, so it has to fit the flight, not the afternoon.
    assert [w.title for w in plan.watch] == ["Short Show"]
    sent = json.dumps(fake.queries)
    assert "TR-1" not in sent and RAHMAN in sent
    out = plan.to_dict(for_traveller=False)
    assert "dietary_needed" not in out and out["dietary_needs_met"] is True


def test_the_terminal_plan_has_food_there_and_a_film_that_ends_before_the_gate(world):
    fake = FakeQloo()
    wait = ground_wait(legs(world, "KS434"), Position.AIRPORT, NOW, {KS434: 60})
    plan = plan_groundtime(wait, taste(loves=[RAHMAN_LOVE]), qloo(fake))
    assert [s.venue.name for s in plan.stops] == ["Gate Cafe"]
    assert plan.rejected["not a place to eat"] == 1
    films = [w for w in plan.watch if w.kind == "film"]
    assert [w.title for w in films] == ["Short Film"]  # the 240-min epic would miss the gate
    assert films[0].minutes <= wait.wait_minutes - 20
    assert not any(int(q.get("filter.location.radius", 0)) > 2000 for q in fake.queries)


def test_no_taste_shared_still_plans_and_asks_qloo_for_no_films(world):
    fake = FakeQloo()
    wait = ground_wait(legs(world, "KS434"), Position.AWAY, NOW, {KS434: 300})
    plan = plan_groundtime(wait, taste(), qloo(fake))
    assert plan.stops and plan.watch == ()
    assert not any(q.get("filter.type") == "urn:entity:movie" for q in fake.queries)
    assert "Share a few things you love" in plan.note


def test_the_demo_travellers_are_valid():
    travellers = load_travellers()
    assert set(travellers) == {"TR-1001", "TR-1002", "TR-1003", "TR-1004"}
    assert travellers["TR-1003"].taste.dietary == {"jain"}
    assert travellers["TR-1004"].flight_nos == ()  # books in the app


# -- The service, over a real (fake AWS) table ------------------------------


def service(world, fake, table):
    return Groundtime(table, qloo(fake), lambda: world.flights, clock=lambda: NOW)


def test_customer_care_records_a_delay_and_sees_every_traveller_on_the_flight(world, ops_table):
    gt = service(world, FakeQloo(), ops_table)
    recorded = gt.record_delay(KS434, 240, "Late inbound aircraft", "neha.joshi")
    assert recorded["delay_minutes"] == 240 and recorded["waiting"] == 2  # Aarav and Sara
    assert gt.delays() == {KS434: 240}
    board = {r["flight_id"]: r for r in gt.flight_board()}
    assert board[KS434]["delay_minutes"] == 240 and board[KS434]["with_app"] == 2
    [delayed] = gt.delayed_flights()
    assert delayed["reason"] == "Late inbound aircraft" and delayed["recorded_by"] == "neha.joshi"
    care = gt.flight_care(KS434)
    assert sorted(r["name"] for r in care["travellers"]) == ["Aarav Kapoor", "Sara Fernandes"]
    assert care["by_mode"] == {"city": 1, "terminal": 1}
    summaries = sorted(r["wait"]["staff_summary"] for r in care["travellers"])
    assert summaries == [
        "At the airport: a plan inside the terminal, at the gate by 19:20.",
        "Not at the airport yet: an outing near it on the way in, at the terminal by 18:20.",
    ]
    assert all("dietary_needed" not in r for r in care["travellers"])
    gt.record_delay(KS434, 0, "", "neha.joshi")
    assert gt.delays() == {} and trip_store.all_delays(ops_table) == {}


def test_a_delay_is_refused_for_a_flight_that_has_left(world, ops_table):
    from crewops.taste.service import GroundtimeError

    gt = service(world, FakeQloo(), ops_table)
    with pytest.raises(GroundtimeError):
        gt.record_delay("KS432-2026-10-13", 30, "", "neha.joshi")  # left at 11:30
    with pytest.raises(GroundtimeError):
        gt.record_delay(KS434, 13 * 60, "", "neha.joshi")


def test_booking_saves_the_trip_and_the_taste_together_and_only_when_valid(world, ops_table):
    from crewops.taste.profile import ProfileError

    gt = service(world, FakeQloo(), ops_table)
    assert gt.my_trip("TR-1004") == {"booked": False}
    with pytest.raises(ProfileError):
        gt.book("TR-1004", "tr1004.das", "Rahul Das", [KS434], "away", {"dietary": ["paleo"]})
    assert trip_store.booking_of(ops_table, "TR-1004") is None  # nothing kept from a failure
    out = gt.book(
        "TR-1004", "tr1004.das", "Rahul Das", [KS434], "away",
        {"loves": [RAHMAN_LOVE], "dietary": ["vegan"]},
    )  # fmt: skip
    assert out["booking"]["flight_ids"] == [KS434] and out["taste"]["dietary"] == ["vegan"]
    mine = gt.my_trip("TR-1004")
    assert mine["booked"] and mine["legs"][0]["flight_no"] == "KS434"
    assert mine["wait"]["headline"].startswith("No delay on KS434")
    gt.set_position("TR-1004", "airport")
    assert gt.wait("TR-1004").position is Position.AIRPORT


def test_booking_refuses_flights_that_dont_connect_or_leave_too_soon(world, ops_table):
    from crewops.taste.service import GroundtimeError

    gt = service(world, FakeQloo(), ops_table)
    for flights in (["KS432-2026-10-13"], [KS434, "KS588-2026-10-13"], []):
        with pytest.raises(GroundtimeError):
            gt.book("TR-1004", "tr1004.das", "Rahul Das", flights, "away", {})


def test_a_demo_booking_becomes_theirs_when_they_say_where_they_are(world, ops_table):
    gt = service(world, FakeQloo(), ops_table)
    assert gt.wait("TR-1001").position is Position.AWAY
    gt.set_position("TR-1001", "airport")
    saved = trip_store.booking_of(ops_table, "TR-1001")
    assert saved["flight_ids"] == [KS434] and saved["position"] == "airport"


def test_the_short_list_is_qloo_ids_looked_up_by_name(world, ops_table):
    class Search:
        def __call__(self, url, headers, timeout):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            name = q["query"][0]
            if name == "Coldplay":
                return 200, json.dumps({"results": []}).encode(), {}
            result = {"entity_id": f"id-{name}", "name": name, "properties": {}}
            return 200, json.dumps({"results": [result]}).encode(), {}

    options = service(world, Search(), ops_table).taste_options()
    names = [p["name"] for p in options["picks"]]
    assert "Lagaan" in names and "Coldplay" not in names
    assert {d["id"] for d in options["dietary"]} >= {"vegetarian", "jain"}


# -- The concierge ------------------------------------------------------------


class FakeNova:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


def tool_use(name, args=None):
    return {
        "stopReason": "tool_use",
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t1", "name": name, "input": args or {}}}]}},
    }  # fmt: skip


def say(text):
    return {
        "stopReason": "end_turn",
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
    }


@pytest.fixture
def delayed(world, ops_table):
    gt = service(world, FakeQloo(), ops_table)
    gt.record_delay(KS434, 240, "", "neha.joshi")
    return gt


def test_the_concierge_answers_from_its_tools(delayed):
    nova = FakeNova(
        [
            tool_use("plan_groundtime"),
            say("Visit Fort Walk, then lunch at Veg Thali. Be at the terminal by 18:20."),
        ]
    )
    answer = Concierge(delayed, nova, "nova").ask("TR-1001", "What can I do?")
    assert answer.source == "model" and answer.tools == ["plan_groundtime"]
    assert "Fort Walk" in answer.text
    result = nova.calls[1]["messages"][2]["content"][0]["toolResult"]
    assert result["status"] == "success" and "Veg Thali" in result["content"][0]["text"]


def test_the_concierge_records_where_the_traveller_says_they_are(delayed):
    nova = FakeNova(
        [
            tool_use("set_position", {"position": "airport"}),
            tool_use("plan_groundtime"),
            say("Gate Cafe is open now. Be at the gate by 19:20."),
        ]
    )
    answer = Concierge(delayed, nova, "nova").ask("TR-1001", "I'm already at the airport")
    assert answer.source == "model" and "Gate Cafe" in answer.text
    assert delayed.wait("TR-1001").position is Position.AIRPORT


def test_a_made_up_place_is_caught_and_the_checked_plan_answers_instead(delayed):
    nova = FakeNova(
        [tool_use("plan_groundtime"), say("Try Taj Mahal Palace for dinner, then Fort Walk.")]
    )
    answer = Concierge(delayed, nova, "nova").ask("TR-1001", "What can I do?")
    assert answer.source == "plan" and "Taj Mahal Palace" not in answer.text
    assert "Fort Walk" in answer.text and any("Taj Mahal Palace" in n for n in answer.notes)
    assert answer.text.startswith("You haven't left for the airport yet.")


def test_without_a_model_the_plan_is_written_out(delayed):
    answer = Concierge(delayed, None, None).ask("TR-1002", "Anything?")
    assert answer.source == "plan"
    # Four hours late and already at the airport: even the long film ends before the gate.
    assert answer.text.startswith("You're at Goa airport.") and "Long Epic" in answer.text


def test_grounding_accepts_sentence_openers_and_rejects_strangers():
    results = ['{"name": "Cansaulim Beach"}']
    assert grounded("Then Cansaulim Beach at 15:00.", results, "") == []
    assert grounded("Try Baga Beach Shack.", results, "") == ["Try Baga Beach Shack"]


# -- Who may do what -----------------------------------------------------------


def test_each_role_sees_only_its_own_part(world, delayed, ops_table):
    api = GroundtimeApi(ops_table, lambda: world, groundtime=delayed, qloo=qloo(FakeQloo()))
    sara = Caller("tr1002.fernandes", frozenset({Role.TRAVELLER}), traveller_id="TR-1002")
    plan = api.my_groundtime(sara)
    assert plan["traveller"]["name"] == "Sara Fernandes" and plan["wait"]["mode"] == "terminal"
    assert api.ask(sara, "Anything to watch?")["source"] == "plan"
    care = Caller("neha.joshi", frozenset({Role.CUSTOMER_CARE}))
    crew = Caller("c1042.nair", frozenset({Role.CREW}), crew_id="C-1042")
    for call in (
        lambda: api.flight_care(sara, KS434),
        lambda: api.record_delay(sara, KS434, 30),
        lambda: api.my_groundtime(care),
        lambda: api.my_flights(sara),
        lambda: api.team_accounts(care),
        lambda: api.book_trip(crew, [KS434], {}),
    ):
        with pytest.raises(ApiError) as err:
            call()
        assert err.value.code == "FORBIDDEN"
    assert len(api.flight_care(care, KS434)["travellers"]) == 2
    nobody = Caller("tr1004.das", frozenset({Role.TRAVELLER}), traveller_id="TR-1004")
    with pytest.raises(ApiError) as err:
        api.my_groundtime(nobody)
    assert err.value.code == "NOT_FOUND"


def test_crew_see_their_own_flights_with_delays(world, delayed, ops_table):
    api = GroundtimeApi(ops_table, lambda: world, groundtime=delayed, qloo=qloo(FakeQloo()))
    pairing = next(p for p in world.pairings.values() if KS434 in p.flight_ids)
    crew_id = pairing.crew[0].crew_id
    mine = api.my_flights(Caller("c", frozenset({Role.CREW}), crew_id=crew_id))
    legs = [leg for d in mine["days"] for leg in d["legs"]]
    assert any(leg["flight_id"] == KS434 and leg["delay_minutes"] == 240 for leg in legs)
