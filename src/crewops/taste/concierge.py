"""The Groundtime concierge: a traveller's questions, answered by an agent with Qloo tools.

Nova decides what to look up, through tools that only ever return checked facts: the
traveller's wait from their booking and the recorded delays, the plan (Qloo's picks after
every check in ``crewops.taste.groundtime``), films and series that fit a given number of
minutes, and Qloo's catalogue for "something like ...". The model words the answer; it never
picks a place itself.

Before an answer is given, every name in it that looks like a place or a title is matched
against what the tools returned. One that isn't there means the model made something up, and
the traveller gets the plan written out from the checked facts instead. Without models, or if
the model service is down, they get that written-out plan straight away.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from crewops.taste.groundtime import WATCH_MARGIN_MINUTES, GroundPlan
from crewops.taste.qloo import QlooError
from crewops.taste.service import SEARCH_TYPES, Groundtime, GroundtimeError
from crewops.taste.travellers import Position

MAX_ROUNDS = 5
MAX_RESULT_CHARS = 8000

SYSTEM = """\
You are Groundtime, an airline's assistant for passengers who are waiting: a delay, or a
long connection. Answer the signed-in traveller about their own trip only.

Rules:
- Every place, film, series and time you mention must come from a tool result. Never add
  one of your own, and never change a time.
- If the traveller is at the airport or connecting, never suggest leaving it: Indian airports
  only let a passenger back out of the departure terminal with clearance.
- Always give the time to be at the terminal door (plan on the way in) or at the gate.
- If they say where they are now ("I'm at the airport", "still at the hotel"), call
  set_position first, then plan.
- Be brief: a few short lines, the plan in order, times in 24-hour local time.
- Questions about anything other than their wait and their trip: say you can only help with
  their time before the flight."""

TOOLS: list[dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "my_wait",
            "description": "The traveller's current wait: flight, delay, where they are, "
            "whether an outing is possible, and the times to be at the terminal and gate.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "plan_groundtime",
            "description": "The checked plan for the wait: stops chosen by Qloo for the "
            "traveller's taste and verified for opening hours, dietary needs and getting "
            "to the terminal in time, plus a film and a series that fit.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "set_position",
            "description": "Record where the traveller is now: away (not at the airport yet) "
            "or airport (already there, or connecting).",
            "inputSchema": {"json": {"type": "object", "properties": {
                "position": {"type": "string", "enum": ["away", "airport"]},
            }, "required": ["position"]}},
        }
    },
    {
        "toolSpec": {
            "name": "find_to_watch",
            "description": "Films or series matched to the traveller's taste by Qloo, only "
            "those short enough for the minutes given.",
            "inputSchema": {"json": {"type": "object", "properties": {
                "kind": {"type": "string", "enum": ["film", "series"]},
                "minutes": {"type": "integer", "minimum": 20, "maximum": 900},
                "like": {"type": "string", "description": "Optional: a title or artist they "
                         "name, looked up in Qloo and used as the taste signal instead."},
            }, "required": ["kind", "minutes"]}},
        }
    },
    {
        "toolSpec": {
            "name": "search_catalogue",
            "description": "Look something up in Qloo's catalogue by name.",
            "inputSchema": {"json": {"type": "object", "properties": {
                "query": {"type": "string"},
                "kind": {"type": "string", "enum": sorted(SEARCH_TYPES)},
            }, "required": ["query", "kind"]}},
        }
    },
]  # fmt: skip

KINDS = {"film": "urn:entity:movie", "series": "urn:entity:tv_show"}
CAPITALISED = re.compile(r"(?:[A-Z][\w'&-]*\s+){1,6}[A-Z][\w'&-]*")
"""Runs of two or more capitalised words: how place names and titles look in an answer."""


_AWAY = re.compile(
    r"\b(not (yet )?at the airport|haven'?t left|have not left|still (at home|at the hotel|in town)"
    r"|on my way|leaving (home|the hotel))\b",
    re.IGNORECASE,
)
_THERE = re.compile(
    r"\b(i'?m at the airport|i am at the airport|(already|now) at the airport|reached the airport"
    r"|in the terminal|at the terminal|through security)\b",
    re.IGNORECASE,
)


def said_position(question: str) -> Position | None:
    """Where a question says the traveller is, when it says so plainly; else None."""
    if _AWAY.search(question):
        return Position.AWAY
    if _THERE.search(question):
        return Position.AIRPORT
    return None


@dataclass(slots=True)
class ConciergeAnswer:
    text: str
    source: str
    """``model`` (Nova wrote it from checked tool results) or ``plan`` (written out here)."""
    tools: list[str] = field(default_factory=list)
    model_calls: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.text,
            "verified": True,
            "source": self.source,
            "tools": self.tools,
            "model_calls": self.model_calls,
            "notes": self.notes,
        }


def write_out(plan: GroundPlan) -> str:
    """The plan as plain sentences, from the checked facts alone."""
    w = plan.wait
    lines = [w.headline]
    if w.stay_reason and w.position.value == "away":
        lines.append(w.stay_reason)
    for s in plan.stops:
        if s.kind == "terminal":
            lines.append(f"In the terminal: {s.venue.name}. " + "; ".join(s.why[:2]) + ".")
        else:
            lines.append(
                f"{s.arrive:%H:%M} to {s.leave:%H:%M}: {s.venue.name} "
                f"({s.ride_minutes} min ride). " + "; ".join(s.why[:2]) + "."
            )
    if plan.head_back_by and plan.back_at_terminal:
        lines.append(
            f"Leave for the airport by {plan.head_back_by:%H:%M}; you'll be at the terminal "
            f"by {plan.back_at_terminal:%H:%M} (needed by {w.at_terminal_by:%H:%M})."
        )
    for x in plan.watch:
        length = f"{x.minutes} min" if x.kind == "film" else f"{x.minutes}-min episodes"
        lines.append(f"To watch: {x.title} ({x.kind}, {length}).")
    if plan.note:
        lines.append(plan.note)
    return "\n".join(lines)


def _known(results: list[str], question: str) -> str:
    return " ".join([question, *results]).lower()


def grounded(answer: str, results: list[str], question: str) -> list[str]:
    """Names in ``answer`` that no tool returned. Empty means the answer is grounded.

    A capitalised run passes if it, or it without its first word (a sentence's opening
    "Try" or "Then"), appears in a tool result or the question.
    """
    known = _known(results, question)
    unknown = []
    for match in CAPITALISED.finditer(answer):
        run = match.group(0).strip()
        words = run.split()
        if run.lower() in known or " ".join(words[1:]).lower() in known:
            continue
        if len(words) > 2 and " ".join(words[1:-1]).lower() in known:
            continue
        unknown.append(run)
    return unknown


class Concierge:
    def __init__(
        self,
        groundtime: Groundtime,
        client: Any | None,
        model_id: str | None,
        *,
        budget_seconds: float = 25.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """``client`` is a Bedrock runtime client; without one, answers are written out."""
        self.groundtime = groundtime
        self.client = client
        self.model_id = model_id
        self.budget_seconds = budget_seconds
        self.clock = clock

    def _run(self, traveller: str, name: str, args: dict[str, Any]) -> Any:
        gt = self.groundtime
        if name == "my_wait":
            return gt.wait(traveller).to_dict()
        if name == "plan_groundtime":
            return gt.plan(traveller).to_dict(for_traveller=True)
        if name == "set_position":
            return gt.set_position(traveller, str(args.get("position") or ""))
        if name == "search_catalogue":
            return gt.search(str(args.get("query") or ""), str(args.get("kind") or ""))
        if name == "find_to_watch":
            return self._watch(traveller, args)
        raise GroundtimeError("INVALID", f"no tool {name}")

    def _watch(self, traveller: str, args: dict[str, Any]) -> list[dict[str, Any]]:
        kind = args.get("kind")
        if kind not in KINDS:
            raise GroundtimeError("INVALID", "kind is film or series")
        minutes = int(args.get("minutes") or 0)
        taste = self.groundtime.taste(traveller)
        ids = [love.id for love in taste.loves if not love.is_tag]
        if like := str(args.get("like") or "").strip():
            for search_kind in ("urn:entity:movie", "urn:entity:artist", "urn:entity:tv_show"):
                hits = self.groundtime.search(like, search_kind)
                if hits:
                    ids = [hits[0]["id"]]
                    break
        if not ids:
            return []
        body = self.groundtime.qloo.insights(
            {"filter.type": KINDS[kind], "signal.interests.entities": ",".join(ids), "take": 15}
        )
        out = []
        for e in (body.get("results") or {}).get("entities") or ():
            length = (e.get("properties") or {}).get("duration")
            if not isinstance(length, int | float) or length > minutes - WATCH_MARGIN_MINUTES:
                continue
            out.append(
                {
                    "title": e.get("name"),
                    "minutes": int(length),
                    "year": (e.get("properties") or {}).get("release_year"),
                    "affinity": (e.get("query") or {}).get("affinity"),
                }
            )
        return out[:5]

    def ask(self, traveller: str, question: str) -> ConciergeAnswer:
        """``traveller`` is the signed-in traveller's id."""
        question = (question or "").strip()[:500]
        if not question:
            raise GroundtimeError("INVALID", "ask a question")
        if self.client is None or not self.model_id:
            return self._written_out(traveller, question, "no model configured")
        try:
            return self._agent(traveller, question)
        except GroundtimeError:
            raise
        except Exception as exc:  # the model service; the checked plan still answers
            return self._written_out(
                traveller, question, f"model unavailable: {type(exc).__name__}"
            )

    def _written_out(self, traveller: str, question: str, why: str) -> ConciergeAnswer:
        """The checked plan, without the model. Where the traveller says they are still
        counts: "I'm at the airport" moves them before the plan is made."""
        tools = ["plan_groundtime"]
        said = said_position(question)
        booked = self.groundtime.booked(traveller)
        if said is not None and booked is not None and booked.position is not said:
            self.groundtime.set_position(traveller, said.value)
            tools.insert(0, "set_position")
        plan = self.groundtime.plan(traveller)
        return ConciergeAnswer(write_out(plan), "plan", tools, 0, [why])

    def _agent(self, traveller: str, question: str) -> ConciergeAnswer:
        deadline = self.clock() + self.budget_seconds
        messages: list[dict[str, Any]] = [{"role": "user", "content": [{"text": question}]}]
        used: list[str] = []
        results: list[str] = []
        calls = 0
        for _ in range(MAX_ROUNDS):
            if self.clock() > deadline:
                break
            response = self.client.converse(
                modelId=self.model_id,
                system=[{"text": SYSTEM}],
                messages=messages,
                toolConfig={"tools": TOOLS},
                inferenceConfig={"maxTokens": 700, "temperature": 0},
            )
            calls += 1
            message = response["output"]["message"]
            if response.get("stopReason") != "tool_use":
                text = "\n".join(
                    b["text"] for b in message.get("content", []) if "text" in b
                ).strip()
                if response.get("stopReason") not in ("end_turn", "stop_sequence") or not text:
                    break
                unknown = grounded(text, results, question)
                if unknown:
                    answer = self._written_out(
                        traveller, question, "model named " + ", ".join(unknown[:3])
                    )
                    answer.tools = used + answer.tools
                    answer.model_calls = calls
                    return answer
                return ConciergeAnswer(text, "model", used, calls)
            messages.append({"role": "assistant", "content": message["content"]})
            replies = []
            for block in message["content"]:
                use = block.get("toolUse")
                if not use:
                    continue
                used.append(use["name"])
                try:
                    out = self._run(traveller, use["name"], use.get("input") or {})
                    text, status = json.dumps(out, default=str)[:MAX_RESULT_CHARS], "success"
                    results.append(text)
                except (GroundtimeError, QlooError) as exc:
                    text, status = json.dumps({"error": str(exc)}), "error"
                replies.append(
                    {
                        "toolResult": {
                            "toolUseId": use["toolUseId"],
                            "content": [{"text": text}],
                            "status": status,
                        }
                    }
                )
            messages.append({"role": "user", "content": replies})
        answer = self._written_out(traveller, question, "the agent ran out of time")
        answer.tools = used + answer.tools
        answer.model_calls = calls
        return answer
