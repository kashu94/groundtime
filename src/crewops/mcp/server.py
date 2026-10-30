"""The MCP server, as AgentCore Runtime hosts it: stateless streamable HTTP on
``0.0.0.0:8000/mcp``.

Every tool call is made as the signed-in user. AgentCore's authorizer admits only access
tokens from the team's Cognito pool and app client and passes the ``Authorization`` header
through; the server verifies that token again and builds the caller from the token's groups
and the user's profile. A request without a valid token does nothing.

Run locally (``python -m crewops.mcp.server``) it serves the same tools on the same port,
on 127.0.0.1 only, still requiring tokens from the configured pool.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import anyio
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from crewops.auth.identity import AuthError, caller_from_claims
from crewops.auth.tokens import TokenVerifier, bearer
from crewops.domain import Caller
from crewops.mcp.api import ApiError, GroundtimeApi

log = logging.getLogger(__name__)

INSTRUCTIONS = """\
Groundtime turns a flight delay into time well spent. A traveller books a trip and, when they
confirm it, shares a few things they love; `my_groundtime` is then their wait (a delay or a
connection) and a plan for it: places, food and films picked by Qloo for their taste, each
checked for opening hours, dietary needs and getting to the gate in time. Someone already at
the airport is never sent out of it. `ask` is the traveller's concierge. Crew get the same
care on a layover (`my_layover`). Customer care records delays (`record_delay`) and sees
every waiting passenger's plan (`flight_care`). The tools available depend on the signed-in
user's role."""

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
COMMIT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)
QLOO = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
"""Reads only, but asks Qloo, outside Groundtime (with ids and places, never a person)."""


class Gate:
    """Turns a request into a ``Caller``, or refuses it."""

    def __init__(self, verifier: TokenVerifier, profiles: Any) -> None:
        self.verifier = verifier
        self.profiles = profiles

    def caller(self, ctx: Context) -> Caller:
        request = getattr(ctx.request_context, "request", None)
        header = request.headers.get("authorization") if request is not None else None
        try:
            claims = self.verifier.claims(bearer(header))
            return caller_from_claims(
                claims,
                self.profiles,
                issuer=self.verifier.issuer,
                client_id=self.verifier.client_id,
            )
        except AuthError as exc:
            raise ToolError(f"UNAUTHORIZED: {exc}") from None


def build_server(
    api: GroundtimeApi, gate: Gate, *, host: str = "127.0.0.1", port: int = 8000
) -> FastMCP:
    mcp = FastMCP(
        "Groundtime",
        instructions=INSTRUCTIONS,
        host=host,
        port=port,
        stateless_http=True,
    )

    async def run(ctx: Context, call: Any) -> Any:
        # Token check and call both block (key fetch, DynamoDB, Qloo, Bedrock), so they go
        # to a worker thread. The event loop has to stay free for health pings.

        def work() -> Any:
            try:
                return call(gate.caller(ctx))
            except ToolError:
                raise
            except ApiError as exc:
                raise ToolError(f"{exc.code}: {exc.message}") from None
            except Exception:
                log.exception("MCP tool call failed")
                raise ToolError("INTERNAL: something went wrong; it has been logged") from None

        return await anyio.to_thread.run_sync(work)

    @mcp.tool(annotations=READ)
    async def whoami(ctx: Context) -> dict:
        """The signed-in person as the server sees them: username, roles, and the crew or
        passenger record they stand for."""
        return await run(ctx, lambda c: api.whoami(c))

    # -- Travellers ---------------------------------------------------------

    @mcp.tool(annotations=READ)
    async def stations(ctx: Context) -> list:
        """The airports the network flies between: code, city and terminal."""
        return await run(ctx, lambda c: api.stations(c))

    @mcp.tool(annotations=READ)
    async def find_flights(origin: str, destination: str, date: str, ctx: Context) -> list:
        """Traveller: trips from `origin` to `destination` (station codes, e.g. GOI, BLR)
        leaving on `date` (YYYY-MM-DD): direct flights first, then one-stop trips with a
        same-day connection. Each has the `flight_ids` to book."""
        return await run(ctx, lambda c: api.find_flights(c, origin, destination, date))

    @mcp.tool(annotations=QLOO)
    async def taste_options(ctx: Context) -> dict:
        """Traveller or crew: the short list to pick from (artists, films, series and books,
        each a Qloo id) and the dietary needs Groundtime can check for."""
        return await run(ctx, lambda c: api.taste_options(c))

    @mcp.tool(annotations=WRITE)
    async def book_trip(
        flight_ids: list[str],
        ctx: Context,
        loves: list[dict] | None = None,
        dietary: list[str] | None = None,
        position: str = "away",
    ) -> dict:
        """Traveller: confirm a trip (`flight_ids` from `find_flights`) and, with it, up to
        five things you love (each {"id", "name", "type"} from `taste_options` or
        `taste_search`) and dietary needs (vegetarian, vegan, jain, halal, gluten_free).
        Both are saved only now, together. Replaces any earlier booking."""
        taste = {"loves": loves or [], "dietary": dietary or []}
        return await run(ctx, lambda c: api.book_trip(c, flight_ids, taste, position))

    @mcp.tool(annotations=READ)
    async def my_trip(ctx: Context) -> dict:
        """Traveller: your booking, the latest on each flight, your wait in plain words, and
        your saved taste. No Qloo call."""
        return await run(ctx, lambda c: api.my_trip(c))

    @mcp.tool(annotations=WRITE)
    async def set_position(position: str, ctx: Context) -> dict:
        """Traveller: where you are now. `away` (not at the airport yet: a delay can be spent
        near it, on the way in) or `airport` (already there: the plan stays inside, because
        Indian airports only let a passenger back out with clearance)."""
        return await run(ctx, lambda c: api.set_position(c, position))

    @mcp.tool(annotations=QLOO)
    async def my_groundtime(ctx: Context) -> dict:
        """Traveller: your wait and the plan for it. Places, food and films come from Qloo
        for your taste; every stop is checked for opening hours, your dietary needs and
        getting to the terminal or gate in time."""
        return await run(ctx, lambda c: api.my_groundtime(c))

    @mcp.tool(annotations=QLOO)
    async def ask(question: str, ctx: Context) -> dict:
        """Traveller: ask the Groundtime concierge about your wait in plain words. It plans
        with the tools above and names nothing they didn't return; if it can't, you get the
        checked plan written out instead."""
        return await run(ctx, lambda c: api.ask(c, question))

    @mcp.tool(annotations=READ)
    async def my_taste(ctx: Context) -> dict:
        """Traveller or crew: the things you love and your dietary needs, as saved."""
        return await run(ctx, lambda c: api.my_taste(c))

    @mcp.tool(annotations=WRITE)
    async def save_my_taste(
        ctx: Context,
        loves: list[dict] | None = None,
        dietary: list[str] | None = None,
        wind_down: str = "",
    ) -> dict:
        """Traveller or crew: replace your taste: up to five things you love (Qloo ids),
        dietary needs and, for crew, wind_down (quiet or lively)."""
        body = {"loves": loves or [], "dietary": dietary or [], "wind_down": wind_down or None}
        return await run(ctx, lambda c: api.save_my_taste(c, body))

    @mcp.tool(annotations=QLOO)
    async def taste_search(query: str, kind: str, ctx: Context) -> list:
        """Traveller or crew: find something you love in Qloo's catalogue. kind is one of
        urn:entity:artist, urn:entity:movie, urn:entity:tv_show, urn:entity:book,
        urn:entity:podcast or urn:entity:place."""
        return await run(ctx, lambda c: api.taste_search(c, query, kind))

    # -- Crew ---------------------------------------------------------------

    @mcp.tool(annotations=READ)
    async def my_flights(ctx: Context) -> dict:
        """Crew: your duty days for the week ahead, each flight with any recorded delay."""
        return await run(ctx, lambda c: api.my_flights(c))

    @mcp.tool(annotations=QLOO)
    async def my_layover(ctx: Context) -> dict:
        """Crew: places to eat near the crew hotel on your next night stop, within your rest
        (free time, sleep before the next report). A delay moves the evening with it."""
        return await run(ctx, lambda c: api.my_layover(c))

    # -- Customer care ------------------------------------------------------

    @mcp.tool(annotations=READ)
    async def flight_board(ctx: Context, date: str = "") -> list:
        """Customer care: every departure on `date` (YYYY-MM-DD, today if empty) with its
        delay and how many Groundtime travellers are on it."""
        return await run(ctx, lambda c: api.flight_board(c, date))

    @mcp.tool(annotations=WRITE)
    async def record_delay(
        flight_id: str, delay_minutes: int, ctx: Context, reason: str = ""
    ) -> dict:
        """Customer care: record a delay as operations confirm it (e.g. KS434-2026-10-30,
        240), replacing any earlier one; 0 clears it. Every plan on the flight changes."""
        return await run(ctx, lambda c: api.record_delay(c, flight_id, delay_minutes, reason))

    @mcp.tool(annotations=READ)
    async def delayed_flights(ctx: Context) -> list:
        """Customer care: delayed flights still to leave, with how many are booked and how
        many have Groundtime."""
        return await run(ctx, lambda c: api.delayed_flights(c))

    @mcp.tool(annotations=QLOO)
    async def flight_care(flight_id: str, ctx: Context) -> dict:
        """Customer care: every Groundtime traveller waiting for a flight, with their plan;
        dietary needs show only as met."""
        return await run(ctx, lambda c: api.flight_care(c, flight_id))

    # -- Admin --------------------------------------------------------------

    @mcp.tool(annotations=READ)
    async def team_accounts(ctx: Context) -> list:
        """Admin: every sign-in, its roles, and whether you may reset its password."""
        return await run(ctx, lambda c: api.team_accounts(c))

    @mcp.tool(annotations=COMMIT)
    async def reset_password(username: str, ctx: Context) -> dict:
        """Admin: give an account a new random password, returned once. Not your own, and
        not another admin's."""
        return await run(ctx, lambda c: api.reset_password(c, username))

    return mcp


def from_environment(host: str = "127.0.0.1") -> FastMCP:
    """The deployed server: settings from the environment the stack sets."""
    import boto3

    from crewops.auth.accounts import Accounts
    from crewops.bedrock import MODEL_BREAKER, GuardedClient, bedrock_runtime
    from crewops.config import Settings
    from crewops.network import network
    from crewops.store import table_for
    from crewops.store.taste import TableCache
    from crewops.store.users import get_profile
    from crewops.taste.qloo import client_from_settings

    settings = Settings.from_env()
    if not (settings.issuer and settings.user_pool_client_id):
        raise SystemExit("CREWOPS_USER_POOL_ID and CREWOPS_USER_POOL_CLIENT_ID must be set")
    table = table_for(settings)
    session = boto3.Session(region_name=settings.aws_region)
    qloo = client_from_settings(settings, cache=TableCache(table), session=session)
    concierge = GuardedClient(bedrock_runtime(settings.aws_region), MODEL_BREAKER)
    real_time = os.environ.get("CREWOPS_REAL_TIME") == "1"
    api = GroundtimeApi(
        table,
        network,
        qloo=qloo,
        concierge_model=(concierge, settings.concierge_model_id),
        accounts=Accounts(session.client("cognito-idp"), settings.user_pool_id or ""),
        clock=(lambda: datetime.now(UTC)) if real_time else None,
    )
    gate = Gate(
        TokenVerifier(settings.issuer, settings.user_pool_client_id),
        lambda username: get_profile(table, username),
    )
    return build_server(api, gate, host=host)


def main(host: str = "127.0.0.1") -> None:
    logging.basicConfig(level=logging.INFO)
    from_environment(host).run(transport="streamable-http")


if __name__ == "__main__":
    main()
