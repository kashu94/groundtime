"""The Groundtime assistant: one assistant, with the tools and the guide of the role in use.

A traveller gets the concierge's tools (their wait, the checked plan, where they are,
something to watch, Qloo's catalogue). Crew get their flights and their layover plan.
Customer care get the flight board, the delayed flights and the passengers waiting for one.
An admin gets the accounts. Every role also gets the Groundtime guide for that role: how the
app works, the airport times it plans with, the airlines it covers, and who to call.

Each tool is the same API call the web app makes, as the signed-in user, so the assistant can
never see or do more than the person asking. It only reads: delays are recorded and passwords
reset on their pages, where the person sees exactly what they change. The one exception is a
traveller saying where they are, which only moves their own trip.

It answers questions about Groundtime, the person's own trips or work in it, the airlines and
flights it covers, and air travel; anything else gets a fixed reply. A name in an answer that
no tool returned means the model made it up, so the person gets the checked summary for their
role instead. Without the model the summary is the answer.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from crewops.domain.roles import Caller, Role
from crewops.taste.concierge import TOOLS as TRAVELLER_TOOLS
from crewops.taste.concierge import Concierge, grounded, run_agent
from crewops.taste.service import CARE_DESK, MAX_DELAY_TIMES, GroundtimeError
from crewops.taste.stations import AIRPORTS

OFF_TOPIC = (
    "I can only help with Groundtime: your trips, flights and waits, and air travel with the "
    "airlines here. Ask me about one of those."
)
MAX_HISTORY = 6
MAX_TURN_CHARS = 600

LABELS = {
    Role.TRAVELLER: "traveller",
    Role.CREW: "crew member",
    Role.CUSTOMER_CARE: "customer care agent",
    Role.ADMIN: "administrator",
}

COMMON_GUIDE = [
    "Groundtime plans the time a delay or a long connection leaves a passenger, around what "
    "they love, with the Qloo Taste AI API. Every stop is checked for opening hours, dietary "
    "needs and getting to the gate in time.",
    "Airlines: Deccan Express (DX), Konkan Skyways (KS) and Nilgiri Connect (NG), all "
    "domestic within India, so no visa applies. Airports: "
    + ", ".join(f"{a.city} ({a.station})" for a in AIRPORTS.values())
    + ". Flights are on sale up to 31 December 2026. All times are India time.",
    "Airport times Groundtime plans with: be at the terminal door 1 h 40 min before "
    "departure (bag drop and security take 45 minutes); be at the gate 40 minutes before; "
    "the gate closes 25 minutes before departure.",
    "Once inside the departure terminal, Indian airports only let a passenger back out with "
    "the airline's and security's clearance, so someone at the airport gets a plan inside "
    "the terminal. An outing near the airport is only for someone who hasn't left for it yet.",
    f"{CARE_DESK['name']}: {CARE_DESK['phone']}, {CARE_DESK['hours']}. Baggage allowances, "
    "fares, refunds and rebooking are not in Groundtime: call that number.",
]

GUIDES: dict[Role, list[str]] = {
    Role.TRAVELLER: [
        "Booking: My trip, then Book a trip. Choose from and to, a date, a direct flight or "
        "two with a connection of 1 to 6 hours, then tap up to five things you love and any "
        "dietary needs. A flight can be booked up to an hour before it leaves. Nothing is "
        "saved until Confirm booking.",
        "When a flight is delayed, customer care records it and My trip shows the new times. "
        "Plan my time gives the plan; Plan again after anything changes.",
        "Where are you now: tap Not at the airport yet or I'm at the airport, or Use my "
        "location. The location is compared with the airport on the phone and never stored; "
        "only whether you are at the airport is saved.",
        "What you love can be changed any time from My trip with Edit what I love. Qloo only "
        "ever receives the ids of what you love, never your name.",
    ],
    Role.CREW: [
        "The Crew page lists your duty days for the week with report and release times and "
        "any delay on your flights.",
        "Layover plan: somewhere to eat near the crew hotel at your next night stop, inside "
        "the free time your rest leaves (release, the ride to the hotel, and eight hours of "
        "sleep before the ride back). After a long day, places are quieter and closer.",
        "A rest shorter than 12 hours is flagged: tell crew scheduling before planning "
        "anything. A delay on your last flight of the day moves your evening with it.",
        "What you love: set it on the Crew page; the layover picks follow it.",
    ],
    Role.CUSTOMER_CARE: [
        "Flight board: search by flight number, airport or city, and filter to flights still "
        "to leave, delayed, or with Groundtime travellers.",
        f"Record delay: minutes up to 12 hours, and a reason. A flight can be marked late at "
        f"most {MAX_DELAY_TIMES} times; every change shows who made it and when. Clear: back "
        "on time is always allowed. A flight that has left can't be changed.",
        "Delayed now lists delayed flights still to leave. Pick one to see every Groundtime "
        "passenger's plan: near the airport or in the terminal, and whether their dietary "
        "needs are met. Customer care never sees what the needs are.",
        "Delays are recorded on the board itself, not through the assistant.",
    ],
    Role.ADMIN: [
        "The Admin page lists every sign-in with its roles and the passenger or crew record "
        "it is linked to.",
        "Reset password gives a new, generated password for anyone except an admin or "
        "yourself; pass it on to the person by hand. Admin passwords are reset by whoever "
        "holds the AWS account.",
        "Accounts are created from the team file by the provisioning command, not in the app.",
        "Password resets happen on the Admin page, not through the assistant.",
    ],
}

RULES = """\
Rules:
- Answer only about Groundtime, the signed-in person's own trips or work in it, the airlines
  and flights here, and air travel in general (check-in, security, gates, delays,
  connections). For anything else, reply with exactly this and nothing more:
  "{off_topic}"
- Every flight, place, film, person and time you mention must come from a tool result. Never
  add one of your own, and never change a time. Look things up before answering.
- For how Groundtime works, airport times or who to call, use groundtime_guide.
- For baggage, fares, refunds or rebooking, say Groundtime doesn't have that and give the
  customer care number from groundtime_guide.
- Be brief: a few short lines, times in 24-hour India time. Plain text, no markdown."""

PERSONAS = {
    Role.TRAVELLER: """\
You are the Groundtime assistant for a passenger. Help them with their own trip and the wait
a delay or a connection leaves them.
- If they are at the airport or connecting, never suggest leaving it.
- Always give the time to be at the terminal door (plan on the way in) or at the gate.
- If they say where they are now, call set_position first, then plan.""",
    Role.CREW: """\
You are the Groundtime assistant for an airline crew member. Help them with their own duty
days, delays on their flights, and where to eat on their next layover inside their rest.""",
    Role.CUSTOMER_CARE: """\
You are the Groundtime assistant for a customer care agent. Help them find flights and their
delays, and see how waiting passengers are planned for. You can't record a delay: tell them
to use Record delay on the flight board. Never guess a dietary need; you only know whether
needs are met.""",
    Role.ADMIN: """\
You are the Groundtime assistant for an administrator. Help them with the accounts and roles.
You can't reset a password: tell them to use Reset password on the Admin page.""",
}


def _spec(name: str, description: str, properties: Mapping[str, Any] | None = None,
          required: list[str] | None = None) -> dict[str, Any]:  # fmt: skip
    schema: dict[str, Any] = {"type": "object", "properties": dict(properties or {})}
    if required:
        schema["required"] = required
    return {"toolSpec": {"name": name, "description": description,
                         "inputSchema": {"json": schema}}}  # fmt: skip


GUIDE_TOOL = _spec(
    "groundtime_guide",
    "How Groundtime works for this person's role, the airport times it plans with, the "
    "airlines and airports it covers, and the customer care number.",
)
ROLE_TOOLS: dict[Role, list[dict[str, Any]]] = {
    Role.TRAVELLER: [*TRAVELLER_TOOLS, GUIDE_TOOL],
    Role.CREW: [
        _spec("my_flights", "The crew member's duty days for the week: report and release "
              "times, each flight, and any delay recorded on it."),
        _spec("my_layover", "Their next night stop and where to eat near the crew hotel, "
              "chosen by Qloo for their taste and checked to fit their rest."),
        GUIDE_TOOL,
    ],
    Role.CUSTOMER_CARE: [
        _spec("find_flights", "Departures on a day matching a search: a flight number "
              "(KS434), an airport code (GOI) or a city (Goa). Each with its delay, how many "
              "times it has been marked late, and how many Groundtime travellers are on it.",
              {"query": {"type": "string"},
               "date": {"type": "string", "description": "YYYY-MM-DD; today if empty"}},
              ["query"]),
        _spec("delayed_flights", "Every delayed flight still to leave, with its reason and "
              "who recorded it."),
        _spec("flight_care", "Every Groundtime passenger waiting for one flight, with their "
              "plan. Takes the flight_id from find_flights or delayed_flights.",
              {"flight_id": {"type": "string"}}, ["flight_id"]),
        GUIDE_TOOL,
    ],
    Role.ADMIN: [
        _spec("accounts", "Every sign-in: username, name, roles, and whether you may reset "
              "its password."),
        GUIDE_TOOL,
    ],
}  # fmt: skip


@dataclass(slots=True)
class AssistantAnswer:
    text: str
    source: str
    """``model`` (checked against the tools), ``summary`` (written from the tools without
    the model) or ``off_topic``."""
    role: Role
    tools: list[str] = field(default_factory=list)
    model_calls: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.text,
            "source": self.source,
            "role": self.role.value,
            "tools": self.tools,
            "model_calls": self.model_calls,
            "notes": self.notes,
        }


def role_for(caller: Caller, asked: str = "") -> Role:
    """The role the assistant serves: the one asked for, if the caller holds it, else their
    first in the order traveller, crew, customer care, admin."""
    if asked:
        try:
            role = Role(asked)
        except ValueError:
            raise GroundtimeError("INVALID", f"no role {asked!r}") from None
        if role not in caller.roles:
            raise GroundtimeError("FORBIDDEN", f"you don't hold the {asked} role")
        return role
    for role in (Role.TRAVELLER, Role.CREW, Role.CUSTOMER_CARE, Role.ADMIN):
        if role in caller.roles:
            return role
    raise GroundtimeError("FORBIDDEN", "this sign-in holds no role")


def history_messages(history: Any) -> list[dict[str, Any]]:
    """The last few turns of the conversation, as Converse messages: alternating, starting
    with the user, each turn cut short. Anything malformed is dropped."""
    turns = []
    for turn in (history if isinstance(history, list) else [])[-MAX_HISTORY:]:
        if not isinstance(turn, Mapping):
            continue
        who, text = turn.get("role"), str(turn.get("text") or "").strip()
        if who in ("user", "assistant") and text:
            turns.append((who, text[:MAX_TURN_CHARS]))
    out: list[dict[str, Any]] = []
    for who, text in turns:
        if (not out and who != "user") or (out and out[-1]["role"] == who):
            continue
        out.append({"role": who, "content": [{"text": text}]})
    if out and out[-1]["role"] == "user":
        out.pop()  # the new question follows
    return out


def matches(row: Mapping[str, Any], query: str) -> bool:
    """A board row matches when every word of ``query`` is in its flight number, airports
    or cities: "ks434", "KS 434", "goi", "goa bengaluru"."""
    words = re.sub(r"\b([a-z]{2})\s+(\d)", r"\1\2", query.lower()).replace(",", " ").split()
    cities = {a.station: a.city for a in AIRPORTS.values()}
    fields = [str(row.get(k) or "").lower() for k in ("flight_no", "from", "to")] + [
        cities.get(str(row.get(k)), "").lower() for k in ("from", "to")
    ]
    return all(any(w in f for f in fields) for w in words)


class Assistant:
    def __init__(
        self,
        api: Any,
        client: Any | None,
        model_id: str | None,
        *,
        budget_seconds: float = 25.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """``api`` is the GroundtimeApi the tools call, as the caller; ``client`` a Bedrock
        runtime client (without one, every answer is the summary)."""
        self.api = api
        self.client = client
        self.model_id = model_id
        self.budget_seconds = budget_seconds
        self.clock = clock

    def _concierge(self) -> Concierge:
        return Concierge(self.api.groundtime(), self.client, self.model_id)

    # -- Tools -----------------------------------------------------------------

    def _run(self, caller: Caller, role: Role, name: str, args: dict[str, Any]) -> Any:
        from crewops.mcp.api import ApiError

        if name not in {t["toolSpec"]["name"] for t in ROLE_TOOLS[role]}:
            raise GroundtimeError("INVALID", f"no tool {name} for this role")
        if name == "groundtime_guide":
            return {"for": LABELS[role], "guide": GUIDES[role] + COMMON_GUIDE}
        try:
            if role is Role.TRAVELLER:
                traveller = self.api._traveller(caller)
                return self._concierge()._run(traveller, name, args)
            if name == "my_flights":
                cities = {a.station: a.city for a in AIRPORTS.values()}
                return self.api.my_flights(caller) | {"cities": cities}
            if name == "my_layover":
                return self.api.my_layover(caller)
            if name == "find_flights":
                query = str(args.get("query") or "").strip()
                rows = self.api.flight_board(caller, str(args.get("date") or ""))
                found = [_board_row(r) for r in rows if matches(r, query)]
                return found[:20] or {"found": 0, "searched": query}
            if name == "delayed_flights":
                return [_board_row(r) for r in self.api.delayed_flights(caller)]
            if name == "flight_care":
                care = self.api.flight_care(caller, str(args.get("flight_id") or ""))
                return _care_view(care)
            if name == "accounts":
                return [
                    {k: a[k] for k in ("username", "name", "roles", "may_reset")}
                    for a in self.api.team_accounts(caller)
                ]
        except ApiError as exc:
            raise GroundtimeError(exc.code, exc.message) from None
        raise GroundtimeError("INVALID", f"no tool {name}")

    # -- Answers ---------------------------------------------------------------

    def ask(
        self, caller: Caller, question: str, *, role: str = "", history: Any = None
    ) -> AssistantAnswer:
        serving = role_for(caller, role)
        question = (question or "").strip()[:500]
        if not question:
            raise GroundtimeError("INVALID", "ask a question")
        if self.client is None or not self.model_id:
            return self.summary(caller, serving, question, "no model configured")
        system = PERSONAS[serving] + "\n" + RULES.format(off_topic=OFF_TOPIC)
        earlier = history_messages(history)
        messages = [*earlier, {"role": "user", "content": [{"text": question}]}]
        try:
            run = run_agent(
                self.client,
                self.model_id,
                system,
                ROLE_TOOLS[serving],
                lambda name, args: self._run(caller, serving, name, args),
                messages,
                budget_seconds=self.budget_seconds,
                clock=self.clock,
            )
        except GroundtimeError:
            raise
        except Exception as exc:  # the model service; the summary still answers
            return self.summary(
                caller, serving, question, f"model unavailable: {type(exc).__name__}"
            )
        if run.text is None:
            why = "the assistant ran out of time"
        elif _is_off_topic(run.text):
            return AssistantAnswer(OFF_TOPIC, "off_topic", serving, run.used, run.calls)
        else:
            said = [json.dumps(m["content"]) for m in earlier]
            unknown = grounded(run.text, run.results + said, question)
            if not unknown:
                return AssistantAnswer(run.text, "model", serving, run.used, run.calls)
            why = "model named " + ", ".join(unknown[:3])
        answer = self.summary(caller, serving, question, why)
        answer.tools = run.used + answer.tools
        answer.model_calls = run.calls
        return answer

    def summary(self, caller: Caller, role: Role, question: str, why: str) -> AssistantAnswer:
        """What the role's tools say, written out without the model."""
        try:
            if role is Role.TRAVELLER:
                traveller = self.api._traveller(caller)
                try:
                    plan = self._concierge()._written_out(traveller, question, why)
                except GroundtimeError as exc:
                    if exc.code != "NOT_FOUND":
                        raise
                    return AssistantAnswer(
                        f"{exc.message[0].upper()}{exc.message[1:]}. Book one from My trip.",
                        "summary", role, [], 0, [why],
                    )  # fmt: skip
                return AssistantAnswer(plan.text, "summary", role, plan.tools, 0, [why])
            if role is Role.CREW:
                return AssistantAnswer(
                    _crew_summary(self.api.my_flights(caller)), "summary", role,
                    ["my_flights"], 0, [why],
                )  # fmt: skip
            if role is Role.CUSTOMER_CARE:
                return AssistantAnswer(
                    _care_summary(self.api.delayed_flights(caller)), "summary", role,
                    ["delayed_flights"], 0, [why],
                )  # fmt: skip
            return AssistantAnswer(
                _admin_summary(self.api.team_accounts(caller)), "summary", role,
                ["accounts"], 0, [why],
            )  # fmt: skip
        except GroundtimeError:
            raise
        except Exception as exc:
            from crewops.mcp.api import ApiError

            if isinstance(exc, ApiError):
                raise GroundtimeError(exc.code, exc.message) from None
            raise


def _is_off_topic(text: str) -> bool:
    return text.strip().strip('"').startswith(OFF_TOPIC[:40])


def _board_row(r: Mapping[str, Any]) -> dict[str, Any]:
    keep = ("flight_id", "flight_no", "from", "to", "departs_local", "expected_departure_local",
            "delay_minutes", "left", "booked", "with_app", "reason", "recorded_by",
            "recorded_local", "times_delayed", "delays_left")  # fmt: skip
    cities = {a.station: a.city for a in AIRPORTS.values()}
    return {k: r[k] for k in keep if k in r} | {
        "from_city": cities.get(str(r.get("from"))),
        "to_city": cities.get(str(r.get("to"))),
    }


def _care_view(care: Mapping[str, Any]) -> dict[str, Any]:
    cities = {a.station: a.city for a in AIRPORTS.values()}
    return {
        k: care[k] for k in ("flight_id", "flight_no", "from", "to", "delay_minutes", "booked")
    } | {
        "from_city": cities.get(str(care.get("from"))),
        "to_city": cities.get(str(care.get("to"))),
        "by_mode": care.get("by_mode"),
        "travellers": [
            {
                "name": t.get("name"),
                "summary": (t.get("wait") or {}).get("staff_summary"),
                "plan": [s.get("name") for s in t.get("stops") or ()],
                "watch": [w.get("title") for w in t.get("watch") or ()],
                "dietary_needs_met": t.get("dietary_needs_met"),
            }
            for t in care.get("travellers") or ()
        ],
    }


def _crew_summary(flights: Mapping[str, Any]) -> str:
    days = flights.get("days") or []
    if not days:
        return "You have no duty in the week ahead."
    lines = []
    for d in days[:3]:
        legs = ", ".join(
            f"{x['flight_no']} {x['from']}-{x['to']} {x['departs_local'][-5:]}"
            + (f" ({x['delay_minutes']} min late)" if x.get("delay_minutes") else "")
            for x in d.get("legs") or ()
        )
        lines.append(
            f"{_day(d['date'])}: report {d['report_local'][-5:]}, {legs}; release "
            f"{d['release_local'][-5:]}."
        )
    return "Your next duties:\n" + "\n".join(lines)


def _care_summary(delayed: list[Mapping[str, Any]]) -> str:
    if not delayed:
        return "No delayed flights still to leave."
    lines = [
        f"{f['flight_no']} {f['from']}-{f['to']}: {f['delay_minutes']} min late, now "
        f"{f['expected_departure_local'][-5:]}; {f['with_app']} with Groundtime."
        for f in delayed[:8]
    ]
    return "Delayed now:\n" + "\n".join(lines)


def _admin_summary(accounts: list[Mapping[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for a in accounts:
        for r in a.get("roles") or ():
            counts[r] = counts.get(r, 0) + 1
    parts = ", ".join(f"{n} {r.replace('_', ' ')}" for r, n in sorted(counts.items()))
    return f"{len(accounts)} sign-ins: {parts}."


def _day(iso: str) -> str:
    try:
        return date.fromisoformat(iso[:10]).strftime("%a %d %b")
    except ValueError:
        return iso
