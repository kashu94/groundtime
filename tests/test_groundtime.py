import json
import urllib.parse
from datetime import UTC, datetime

import pytest

from crewops.domain import Report
from crewops.engine.world import build_world
from crewops.ingestion.seed import load_seed
from crewops.store.reports import store_report
from crewops.taste.concierge import Concierge, grounded
from crewops.taste.groundtime import ground_wait, plan_groundtime, ride_minutes
from crewops.taste.profile import TasteProfile
from crewops.taste.qloo import QlooClient
from crewops.taste.service import Groundtime, flight_delays
from crewops.taste.travellers import Position, load_travellers, trip

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
    return build_world(load_seed())


def qloo(fake):
    return QlooClient("https://qloo.example", lambda: "k", transport=fake)


def taste(**d):
    return TasteProfile.from_dict("TR-1", d)


def legs(world, *nos):
    return trip(world.flights, nos, NOW)


def test_a_booking_resolves_to_the_day_the_flight_next_operates(world):
    assert [f.flight_id for f in legs(world, "KS434")] == [KS434]
    connection = legs(world, "KS432", "KS588")
    assert [f.flight_id for f in connection] == ["KS432-2026-10-13", "KS588-2026-10-13"]
    assert trip(world.flights, ("XX999",), NOW) == ()


def test_a_delay_hands_back_time_and_the_deadlines_move_with_it(world):
    on_time = ground_wait(legs(world, "KS434"), Position.AWAY, NOW)
    assert on_time.outside_minutes == 0 and on_time.mode == "terminal"
    late = ground_wait(legs(world, "KS434"), Position.AWAY, NOW, {KS434: 240})
    # 16:00 departure, 4 h late: gate closes 19:35, be there by 19:20, terminal door by 18:20.
    assert f"{late.at_gate_by:%H:%M}" == "19:20" and f"{late.at_terminal_by:%H:%M}" == "18:20"
    assert f"{late.free_from:%H:%M}" == "14:20" and late.outside_minutes == 240
    assert late.mode == "city" and late.can_leave


def test_past_security_nobody_leaves_however_long_the_wait(world):
    wait = ground_wait(legs(world, "KS434"), Position.AIRSIDE, NOW, {KS434: 600})
    assert not wait.can_leave and wait.mode == "terminal"
    assert "past security" in wait.stay_reason


def test_a_connection_is_airside_from_the_arrival(world):
    wait = ground_wait(legs(world, "KS432", "KS588"), Position.AWAY, NOW)
    assert wait.flight.flight_id == "KS588-2026-10-13" and wait.position is Position.AIRSIDE
    assert wait.connecting_from.flight_id == "KS432-2026-10-13"
    assert f"{wait.free_from:%H:%M}" == "13:30"  # landed 13:15 IST, plus getting off


def test_the_city_plan_keeps_only_real_sights_open_meals_and_a_ride_back_in_time(world):
    fake = FakeQloo()
    wait = ground_wait(legs(world, "KS434"), Position.AWAY, NOW, {KS434: 240})
    plan = plan_groundtime(
        wait,
        taste(
            loves=[{"id": RAHMAN, "name": "A. R. Rahman", "type": "urn:entity:artist"}],
            dietary=["vegetarian"],
        ),
        qloo(fake),
    )
    names = [(s.kind, s.venue.name) for s in plan.stops]
    # Both orders fit; the one back at the terminal sooner wins.
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
    wait = ground_wait(legs(world, "KS434"), Position.AIRSIDE, NOW, {KS434: 120})
    plan = plan_groundtime(
        wait,
        taste(loves=[{"id": RAHMAN, "name": "A. R. Rahman", "type": "urn:entity:artist"}]),
        qloo(fake),
    )
    assert [s.venue.name for s in plan.stops] == ["Gate Cafe"]
    assert plan.rejected["not a place to eat"] == 1
    films = [w for w in plan.watch if w.kind == "film"]
    assert [w.title for w in films] == ["Short Film"]  # the 240-min epic would miss the gate
    assert films[0].minutes <= wait.wait_minutes - 20


def test_no_taste_shared_still_plans_and_asks_qloo_for_no_films(world):
    fake = FakeQloo()
    wait = ground_wait(legs(world, "KS434"), Position.LANDSIDE, NOW, {KS434: 300})
    plan = plan_groundtime(wait, taste(), qloo(fake))
    assert plan.stops and plan.watch == ()
    assert not any(q.get("filter.type") == "urn:entity:movie" for q in fake.queries)
    assert "Share a few things you love" in plan.note


def test_delays_come_from_reported_disruptions_latest_first(ops_table):
    def report(rid, minutes, at):
        return Report.from_dict({
            "report_id": rid, "type": "flight_delay", "reported_utc": at,
            "reported_by": {"user_id": "u-1", "roles": ["reporter"]},
            "details": {"flight_id": KS434, "delay_minutes": minutes},
        })  # fmt: skip

    store_report(ops_table, report("r-delay-0001", 60, "2026-10-13T06:00:00Z"), NOW)
    store_report(ops_table, report("r-delay-0002", 240, "2026-10-13T07:00:00Z"), NOW)
    assert flight_delays(ops_table) == {KS434: 240}


def service(world, fake, delays=None):
    gt = Groundtime(
        None, qloo(fake), lambda: world.flights, clock=lambda: NOW,
        delays=lambda: delays or {KS434: 240},
    )  # fmt: skip
    gt.taste = lambda t: t.taste  # no table: the booking's own profile
    return gt


def test_customer_care_sees_every_app_traveller_on_the_flight(world):
    care = service(world, FakeQloo()).flight_care(KS434)
    names = sorted(r["name"] for r in care["travellers"])
    assert names == ["Aarav Kapoor", "Rahul Das", "Sara Fernandes"]
    assert care["delay_minutes"] == 240 and care["by_mode"]["terminal"] >= 1
    assert all("dietary_needed" not in r for r in care["travellers"])


def test_the_demo_travellers_are_valid():
    travellers = load_travellers()
    assert {t.traveller_id for t in travellers.values()} == {
        "TR-1001",
        "TR-1002",
        "TR-1003",
        "TR-1004",
    }
    assert travellers["tr1003.shah"].taste.dietary == {"jain"}


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


def test_the_concierge_answers_from_its_tools(world):
    nova = FakeNova(
        [
            tool_use("plan_groundtime", {"position": "away"}),
            say("Visit Fort Walk, then lunch at Veg Thali. Be back at the terminal by 18:20."),
        ]
    )
    answer = Concierge(service(world, FakeQloo()), nova, "nova").ask(
        "tr1001.kapoor", "What can I do?"
    )
    assert answer.source == "model" and answer.tools == ["plan_groundtime"]
    assert "Fort Walk" in answer.text
    result = nova.calls[1]["messages"][2]["content"][0]["toolResult"]
    assert result["status"] == "success" and "Veg Thali" in result["content"][0]["text"]


def test_a_made_up_place_is_caught_and_the_checked_plan_answers_instead(world):
    nova = FakeNova(
        [tool_use("plan_groundtime"), say("Try Taj Mahal Palace for dinner, then Fort Walk.")]
    )
    answer = Concierge(service(world, FakeQloo()), nova, "nova").ask(
        "tr1001.kapoor", "What can I do?"
    )
    assert answer.source == "plan" and "Taj Mahal Palace" not in answer.text
    assert "Fort Walk" in answer.text and any("Taj Mahal Palace" in n for n in answer.notes)


def test_without_a_model_the_plan_is_written_out(world):
    answer = Concierge(service(world, FakeQloo()), None, None).ask("tr1002.fernandes", "Anything?")
    assert answer.source == "plan"
    # Four hours late and already airside: even the long film ends before the gate.
    assert "past security" in answer.text and "Long Epic" in answer.text


def test_grounding_accepts_sentence_openers_and_rejects_strangers():
    results = ['{"name": "Cansaulim Beach"}']
    assert grounded("Then Cansaulim Beach at 15:00.", results, "") == []
    assert grounded("Try Baga Beach Shack.", results, "") == ["Try Baga Beach Shack"]


def test_only_travellers_get_plans_and_their_questions_go_to_the_concierge(world):
    from crewops.domain import Role
    from crewops.mcp.api import ApiError, CrewOpsApi
    from crewops.tools import Caller

    api = CrewOpsApi(None, lambda: None, lambda _: None, groundtime=service(world, FakeQloo()))
    traveller = Caller("tr1002.fernandes", frozenset({Role.TRAVELLER}))
    plan = api.my_groundtime(traveller)
    assert plan["traveller"]["name"] == "Sara Fernandes" and plan["wait"]["mode"] == "terminal"
    answer = api.ask(traveller, "Anything to watch?")
    assert answer["intent"] == "groundtime" and answer["source"] == "plan"
    with pytest.raises(ApiError) as err:
        api.my_groundtime(Caller("rohit.malhotra", frozenset({Role.CONTROLLER}), desk="desk-2"))
    assert err.value.code == "FORBIDDEN"
    with pytest.raises(ApiError) as err:
        api.flight_care(traveller, KS434)
    assert err.value.code == "FORBIDDEN"
    care = api.flight_care(Caller("neha.joshi", frozenset({Role.CUSTOMER_CARE})), KS434)
    assert len(care["travellers"]) == 3
    with pytest.raises(ApiError) as err:
        api.my_groundtime(Caller("tr9999.nobody", frozenset({Role.TRAVELLER})))
    assert err.value.code == "NOT_FOUND"
