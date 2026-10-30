"""What the MCP server can do, as plain methods, each checking who is asking.

Every operation takes the ``Caller`` built from the request's verified token, never what the
user typed. A traveller only ever sees their own trip, a crew member only their own flights
and layovers, and customer care sees every waiting passenger's plan without their dietary
needs. Errors are ``ApiError`` with a code the server turns into a tool error.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from crewops.auth.accounts import AccountError, Accounts, may_reset, new_password
from crewops.bedrock import MODEL_BREAKER
from crewops.domain import Caller, Role
from crewops.ingestion.seed import default_seed_dir
from crewops.network import Network
from crewops.store import taste as taste_store
from crewops.store.users import get_profile, list_profiles
from crewops.taste.concierge import Concierge
from crewops.taste.layover import LayoverError, layover_brief, night_stops
from crewops.taste.profile import ProfileError, TasteProfile
from crewops.taste.qloo import QlooClient, QlooError
from crewops.taste.service import Groundtime, GroundtimeError
from crewops.taste.stations import AIRPORTS, IST

log = logging.getLogger(__name__)

CREW_LOOK_AHEAD_DAYS = 7
SEED_MOMENT = datetime(2026, 10, 13, 7, 30, tzinfo=UTC)
"""13 October, 13:00 in India: "now" for tests and local runs, so they are repeatable."""


class ApiError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _local(at: datetime) -> str:
    return at.astimezone(IST).strftime("%Y-%m-%d %H:%M")


def demo_crew_tastes(path: Path | None = None) -> dict[str, TasteProfile]:
    """Crew taste profiles from ``data/team/demo_tastes.json``, by crew id."""
    path = path or default_seed_dir().parent / "team" / "demo_tastes.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {p["crew_id"]: TasteProfile.from_dict(p["crew_id"], p) for p in raw["profiles"]}


class GroundtimeApi:
    def __init__(
        self,
        table: Any,
        network: Callable[[], Network],
        *,
        qloo: QlooClient | None = None,
        concierge_model: tuple[Any, str] | None = None,
        accounts: Accounts | None = None,
        clock: Callable[[], datetime] | None = None,
        groundtime: Groundtime | None = None,
    ) -> None:
        """``network`` gives the flights and crew trips; ``qloo`` turns on the plans;
        ``concierge_model`` is the (Bedrock client, model id) the traveller's agent uses.
        ``clock`` is real time when deployed and the seed's moment otherwise."""
        self.table = table
        self.network = network
        self.qloo = qloo
        self.accounts = accounts
        self.clock = clock or (lambda: SEED_MOMENT)
        self._concierge_model = concierge_model
        self._groundtime = groundtime
        self._crew_tastes: dict[str, TasteProfile] | None = None

    # ------------------------------------------------------------------
    # Shared
    # ------------------------------------------------------------------

    def whoami(self, caller: Caller) -> dict[str, Any]:
        return {
            "user_id": caller.user_id,
            "roles": sorted(r.value for r in caller.roles),
            "crew_id": caller.crew_id,
            "traveller_id": caller.traveller_id,
        }

    def groundtime(self) -> Groundtime:
        if self._groundtime is None:
            if self.qloo is None:
                raise ApiError("UNAVAILABLE", "Groundtime needs the Qloo API, not set up here")
            self._groundtime = Groundtime(
                self.table, self.qloo, lambda: self.network().flights, clock=self.clock
            )
        return self._groundtime

    @staticmethod
    def _call(call: Callable[[], Any]) -> Any:
        try:
            return call()
        except GroundtimeError as exc:
            raise ApiError(exc.code, exc.message) from None
        except ProfileError as exc:
            raise ApiError("INVALID", str(exc)) from None
        except QlooError as exc:
            raise ApiError(exc.code, exc.message) from None
        except LayoverError as exc:
            raise ApiError("NOT_FOUND", str(exc)) from None

    @staticmethod
    def _need(caller: Caller, role: Role, what: str) -> None:
        if role not in caller.roles:
            raise ApiError("FORBIDDEN", what)

    def _traveller(self, caller: Caller) -> str:
        self._need(caller, Role.TRAVELLER, "for travellers")
        if not caller.traveller_id:
            raise ApiError("FORBIDDEN", "this sign-in is linked to no passenger record")
        return caller.traveller_id

    # ------------------------------------------------------------------
    # Travellers: book, share taste, and plan the wait
    # ------------------------------------------------------------------

    def stations(self, caller: Caller) -> list[dict[str, str]]:
        return [{"code": a.station, "city": a.city, "airport": a.name} for a in AIRPORTS.values()]

    def find_flights(
        self, caller: Caller, origin: str, destination: str, date: str
    ) -> list[dict[str, Any]]:
        self._traveller(caller)
        network = self.network()
        return self._call(
            lambda: self.groundtime().find_trips(origin, destination, date, network.airline_of)
        )

    def taste_options(self, caller: Caller) -> dict[str, Any]:
        self._taster(caller)
        return self._call(lambda: self.groundtime().taste_options())

    def book_trip(
        self,
        caller: Caller,
        flight_ids: list[str],
        taste: Mapping[str, Any],
        position: str = "away",
    ) -> dict[str, Any]:
        traveller = self._traveller(caller)
        profile = get_profile(self.table, caller.user_id) or {}
        name = str(profile.get("name") or caller.user_id)
        return self._call(
            lambda: self.groundtime().book(
                traveller, caller.user_id, name, flight_ids, position, taste
            )
        )

    def my_trip(self, caller: Caller) -> dict[str, Any]:
        traveller = self._traveller(caller)
        return self._call(lambda: self.groundtime().my_trip(traveller))

    def set_position(self, caller: Caller, position: str) -> dict[str, Any]:
        traveller = self._traveller(caller)
        return self._call(lambda: self.groundtime().set_position(traveller, position))

    def my_groundtime(self, caller: Caller) -> dict[str, Any]:
        traveller = self._traveller(caller)
        return self._call(lambda: self.groundtime().my_plan(traveller))

    def ask(self, caller: Caller, question: str) -> dict[str, Any]:
        """The traveller's concierge."""
        traveller = self._traveller(caller)
        client, model_id = self._concierge_model or (None, None)
        concierge = Concierge(self.groundtime(), client, model_id)
        answer = self._call(lambda: concierge.ask(traveller, question))
        return answer.to_dict() | {"models": MODEL_BREAKER.status()}

    # -- Taste, for travellers and crew ---------------------------------

    def _taster(self, caller: Caller) -> str:
        if Role.TRAVELLER in caller.roles and caller.traveller_id:
            return caller.traveller_id
        if Role.CREW in caller.roles and caller.crew_id:
            return caller.crew_id
        raise ApiError("FORBIDDEN", "taste profiles are for travellers and crew")

    def crew_tastes(self) -> dict[str, TasteProfile]:
        if self._crew_tastes is None:
            self._crew_tastes = demo_crew_tastes()
        return self._crew_tastes

    def my_taste(self, caller: Caller) -> dict[str, Any]:
        owner = self._taster(caller)
        if Role.TRAVELLER in caller.roles:
            return self._call(lambda: self.groundtime().my_taste(owner))
        saved = taste_store.profile_of(self.table, owner)
        profile = saved or self.crew_tastes().get(owner) or TasteProfile(owner)
        return {k: v for k, v in profile.to_dict().items() if k != "crew_id"}

    def save_my_taste(self, caller: Caller, body: Mapping[str, Any]) -> dict[str, Any]:
        owner = self._taster(caller)

        def save() -> dict[str, Any]:
            profile = TasteProfile.from_dict(owner, body)
            saved = taste_store.save_profile(self.table, profile, self.clock())
            return {k: v for k, v in saved.to_dict().items() if k != "crew_id"}

        return self._call(save)

    def taste_search(self, caller: Caller, query: str, kind: str) -> list[dict[str, Any]]:
        self._taster(caller)
        return self._call(lambda: self.groundtime().search(query, kind))

    # ------------------------------------------------------------------
    # Crew: their flights, and the layover plan
    # ------------------------------------------------------------------

    def _crew(self, caller: Caller) -> str:
        self._need(caller, Role.CREW, "for crew")
        if not caller.crew_id:
            raise ApiError("FORBIDDEN", "this sign-in is linked to no crew record")
        return caller.crew_id

    def my_flights(self, caller: Caller) -> dict[str, Any]:
        """The crew member's duty days for the week ahead, with any recorded delay."""
        crew_id = self._crew(caller)
        network = self.network()
        now = self.clock()
        delays = self.groundtime().delays() if self.qloo else {}
        days = []
        for pairing in network.pairings.values():
            if crew_id not in {s.crew_id for s in pairing.crew}:
                continue
            role = next(s.role.value for s in pairing.crew if s.crew_id == crew_id)
            for day in pairing.days:
                if day.release_utc < now or day.report_utc > now + timedelta(
                    days=CREW_LOOK_AHEAD_DAYS
                ):
                    continue
                legs = [network.flights[f] for f in day.flight_ids]
                days.append(
                    {
                        "pairing_id": pairing.pairing_id,
                        "date": day.date.isoformat(),
                        "role": role,
                        "report_local": _local(day.report_utc),
                        "release_local": _local(day.release_utc),
                        "legs": [
                            {
                                "flight_id": f.flight_id,
                                "flight_no": f.flight_no,
                                "from": f.dep_station,
                                "to": f.arr_station,
                                "departs_local": _local(f.dep_utc),
                                "arrives_local": _local(f.arr_utc),
                                "delay_minutes": delays.get(f.flight_id, 0),
                            }
                            for f in legs
                        ],
                    }
                )
        crew = network.crew.get(crew_id)
        return {
            "crew_id": crew_id,
            "name": crew.name if crew else None,
            "rank": crew.rank.value if crew else None,
            "base": crew.base if crew else None,
            "days": sorted(days, key=lambda d: d["report_local"]),
        }

    def my_layover(self, caller: Caller) -> dict[str, Any]:
        """The crew member's next night stop and where to eat, within their rest."""
        crew_id = self._crew(caller)
        if self.qloo is None:
            raise ApiError("UNAVAILABLE", "layover plans need the Qloo API, not set up here")
        now = self.clock()
        delays = self.groundtime().delays()
        stops = night_stops(self.network(), crew_id=crew_id, delays=delays)
        upcoming = [s for s in stops if s.next_report_utc > now]
        if not upcoming:
            return {"night_stop": None, "note": "No night stop on your trips this week."}
        stop = upcoming[0]
        saved = taste_store.profiles_of(self.table, [crew_id])
        profile = saved.get(crew_id) or self.crew_tastes().get(crew_id)
        profiles = {crew_id: profile} if profile else {}
        brief = self._call(lambda: layover_brief(stop, profiles, self.qloo))
        return brief.to_dict(for_crew=True)

    # ------------------------------------------------------------------
    # Customer care: delays, and every waiting passenger
    # ------------------------------------------------------------------

    def _care(self, caller: Caller) -> None:
        self._need(caller, Role.CUSTOMER_CARE, "for customer care")

    def flight_board(self, caller: Caller, date: str = "") -> list[dict[str, Any]]:
        self._care(caller)
        return self._call(lambda: self.groundtime().flight_board(date))

    def record_delay(
        self, caller: Caller, flight_id: str, delay_minutes: int, reason: str = ""
    ) -> dict[str, Any]:
        self._care(caller)
        log.info("%s records %s min on %s", caller.user_id, delay_minutes, flight_id)
        return self._call(
            lambda: self.groundtime().record_delay(flight_id, delay_minutes, reason, caller.user_id)
        )

    def delayed_flights(self, caller: Caller) -> list[dict[str, Any]]:
        self._care(caller)
        return self._call(lambda: self.groundtime().delayed_flights())

    def flight_care(self, caller: Caller, flight_id: str) -> dict[str, Any]:
        self._care(caller)
        return self._call(lambda: self.groundtime().flight_care(flight_id))

    # ------------------------------------------------------------------
    # Admin: accounts
    # ------------------------------------------------------------------

    def team_accounts(self, caller: Caller) -> list[dict[str, Any]]:
        """Every sign-in and its roles, with whether this admin may reset its password."""
        self._need(caller, Role.ADMIN, "only an admin sees the accounts")
        out = []
        for p in sorted(list_profiles(self.table), key=lambda p: p.get("username", "")):
            roles = [Role(r) for r in p.get("roles") or [] if r in set(Role)]
            try:
                may_reset(caller.user_id, caller.roles, p["username"], roles)
                resettable = True
            except AccountError:
                resettable = False
            out.append(
                {
                    "username": p["username"],
                    "name": p.get("name"),
                    "roles": [r.value for r in roles],
                    "crew_id": p.get("crew_id"),
                    "traveller_id": p.get("traveller_id"),
                    "may_reset": resettable,
                }
            )
        return out

    def reset_password(self, caller: Caller, username: str) -> dict[str, Any]:
        """Give one account a new random password, shown once to the admin."""
        if self.accounts is None:
            raise ApiError("UNAVAILABLE", "password resets are not set up on this server")
        username = username.strip().lower()
        profile = get_profile(self.table, username)
        if profile is None:
            raise ApiError("NOT_FOUND", f"no account {username}")
        roles = [Role(r) for r in profile.get("roles") or [] if r in set(Role)]
        try:
            may_reset(caller.user_id, caller.roles, username, roles)
            password = new_password()
            self.accounts.set_password(username, password)
        except AccountError as exc:
            raise ApiError(exc.code, exc.message) from None
        log.info("%s reset the password of %s", caller.user_id, username)
        return {"username": username, "password": password, "note": "Shown once. Pass it on."}
