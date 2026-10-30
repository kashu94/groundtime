"""The MCP server: tokens, the tools it lists, and calls made as the signed-in user."""

import json
import time

import anyio
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from crewops.auth.identity import AuthError
from crewops.auth.tokens import TokenVerifier, bearer
from crewops.ingestion.seed import load_seed
from crewops.mcp.api import GroundtimeApi
from crewops.mcp.server import Gate, build_server
from crewops.network import build_network
from crewops.store.users import get_profile, profile_item, put_profile

ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST"
CLIENT = "client-1"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Keys:
    """Stands in for the pool's published keys."""

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


def token(key=KEY, **overrides):
    claims = {
        "token_use": "access",
        "iss": ISSUER,
        "client_id": CLIENT,
        "exp": int(time.time()) + 600,
        "username": "neha",
        "cognito:groups": ["customer_care"],
    } | overrides
    return jwt.encode(claims, key, algorithm="RS256")


VERIFIER = TokenVerifier(ISSUER, CLIENT, keys=Keys())


# -- Tokens -------------------------------------------------------------------------------


def test_a_valid_token_gives_its_claims():
    assert VERIFIER.claims(token())["username"] == "neha"


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: token(key=OTHER_KEY), "invalid token"),
        (lambda: token(exp=int(time.time()) - 1), "invalid token"),
        (lambda: token(iss="https://elsewhere"), "invalid token"),
        (lambda: token(client_id="client-2"), "not an access token for this app client"),
        (lambda: token(token_use="id"), "not an access token"),
        (lambda: "not.a.jwt", "invalid token"),
    ],
)
def test_bad_tokens_are_refused(make, message):
    with pytest.raises(AuthError, match=message):
        VERIFIER.claims(make())


def test_bearer_header():
    assert bearer("Bearer abc") == "abc" and bearer("bearer  abc ") == "abc"
    for header in (None, "", "Basic abc", "Bearer "):
        with pytest.raises(AuthError, match="sign in first"):
            bearer(header)


# -- Over MCP -----------------------------------------------------------------------------

NETWORK = build_network(load_seed())


@pytest.fixture
def api(ops_table):
    return GroundtimeApi(ops_table, lambda: NETWORK)


def mcp_call(server, headers, tool, arguments):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    app = server.streamable_http_app()

    async def run():
        http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            headers=headers,
        )
        async with server.session_manager.run(), http:
            transport = streamable_http_client("http://127.0.0.1:8000/mcp", http_client=http)
            async with transport as (read, write, _), ClientSession(read, write) as session:
                await session.initialize()
                if tool is None:
                    return [t.name for t in (await session.list_tools()).tools]
                return await session.call_tool(tool, arguments)

    return anyio.run(run)


@pytest.fixture
def server(api):
    put_profile(api.table, profile_item("neha", "Neha Joshi", ["customer_care"]))
    return build_server(api, Gate(VERIFIER, lambda u: get_profile(api.table, u)))


def test_tools_are_listed(server):
    names = set(mcp_call(server, {}, None, {}))
    assert {"find_flights", "book_trip", "my_trip", "my_groundtime", "ask"} <= names
    assert {"record_delay", "flight_board", "flight_care", "my_layover", "my_flights"} <= names


def test_a_call_without_a_token_does_nothing(server):
    result = mcp_call(server, {}, "whoami", {})
    assert result.isError and "UNAUTHORIZED" in result.content[0].text


def test_a_signed_in_call_acts_as_that_user(server):
    headers = {"authorization": f"Bearer {token()}"}
    result = mcp_call(server, headers, "whoami", {})
    assert not result.isError
    payload = json.loads(result.content[0].text)
    assert payload["user_id"] == "neha" and payload["roles"] == ["customer_care"]


def test_a_tool_for_another_role_is_refused(server):
    headers = {"authorization": f"Bearer {token()}"}
    refused = mcp_call(server, headers, "my_trip", {})
    assert refused.isError and "FORBIDDEN" in refused.content[0].text


def test_a_forged_token_does_nothing(server):
    forged = {"authorization": f"Bearer {token(key=OTHER_KEY)}"}
    result = mcp_call(server, forged, "whoami", {})
    assert result.isError and "invalid token" in result.content[0].text


def test_an_unexpected_failure_reaches_the_caller_without_internals(server, api, monkeypatch):
    def broken(caller):
        raise RuntimeError("table arn:aws:dynamodb:secret-detail")

    monkeypatch.setattr(api, "whoami", broken)
    headers = {"authorization": f"Bearer {token()}"}
    result = mcp_call(server, headers, "whoami", {})
    text = result.content[0].text
    assert result.isError and "INTERNAL:" in text and "secret-detail" not in text


def test_without_qloo_the_plans_say_so(server):
    headers = {"authorization": f"Bearer {token()}"}
    result = mcp_call(server, headers, "flight_board", {})
    assert result.isError and "UNAVAILABLE" in result.content[0].text


def test_invocation_url_encodes_the_runtime_arn():
    from crewops.mcp.client import invocation_url

    arn = "arn:aws:bedrock-agentcore:us-east-1:111111111111:runtime/groundtime_dev_mcp-AbC"
    assert invocation_url("us-east-1", arn) == (
        "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/"
        "arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A111111111111%3Aruntime%2F"
        "groundtime_dev_mcp-AbC/invocations?qualifier=DEFAULT"
    )


def test_client_shows_results_as_json():
    from crewops.mcp.client import _parsed

    assert _parsed(['{"answer": "yes"}']) == {"answer": "yes"}
    assert _parsed(['{"a": 1}', '{"b": 2}']) == [{"a": 1}, {"b": 2}]
    assert _parsed(["plain words"]) == "plain words"
    assert _parsed([]) == []
    assert _parsed(['{"a": 1}'], as_list=True) == [{"a": 1}]


def test_the_client_knows_which_tools_return_lists(api):
    import inspect

    from crewops.mcp.client import LIST_TOOLS

    server = build_server(api, Gate(VERIFIER, lambda u: None))
    returns_list = {
        t.name
        for t in server._tool_manager.list_tools()
        if inspect.signature(t.fn).return_annotation in (list, "list")
    }
    assert returns_list == LIST_TOOLS


def test_packaged_entry_point_finds_its_data():
    from crewops.mcp.package import MAIN

    compile(MAIN, "main.py", "exec")
    assert "CREWOPS_DATA_DIR" in MAIN and 'main(host="0.0.0.0")' in MAIN
