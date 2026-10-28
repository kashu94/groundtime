import json
import urllib.parse

import pytest

from crewops.config import Settings
from crewops.taste.qloo import MemoryCache, QlooClient, QlooError, guard, key_from_settings


class FakeQloo:
    """Answers with queued (status, body) pairs and records every URL it was asked."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.urls = []
        self.headers = []

    def __call__(self, url, headers, timeout):
        self.urls.append(url)
        self.headers.append(dict(headers))
        status, body = self.answers.pop(0)
        if isinstance(body, Exception):
            raise body
        return status, json.dumps(body).encode(), {}


def client(fake, key="k-test", **kwargs):
    return QlooClient(
        "https://qloo.example", lambda: key, transport=fake, sleep=lambda s: None, **kwargs
    )


def test_the_key_goes_in_a_header_never_the_url():
    fake = FakeQloo((200, {"results": []}))
    client(fake).search("A.R. Rahman", "urn:entity:artist")
    assert fake.headers[0]["X-Api-Key"] == "k-test"
    assert "k-test" not in fake.urls[0]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(fake.urls[0]).query)
    assert query == {"query": ["A.R. Rahman"], "types": ["urn:entity:artist"], "take": ["5"]}


@pytest.mark.parametrize(
    "params",
    [
        {"signal.interests.entities": "C-1042"},
        {"query": "rohit.malhotra@example.com"},
        {"filter.tags": "u-17"},
        {"crew_id": "anything"},
        {"take": 500},
    ],
)
def test_personal_data_and_unknown_parameters_never_leave(params):
    with pytest.raises(QlooError) as err:
        guard(params)
    assert err.value.code == "QLOO_REFUSED"


def test_answers_are_cached_so_a_repeat_costs_nothing():
    fake = FakeQloo((200, {"results": {"entities": []}}))
    qloo = client(fake, cache=MemoryCache())
    params = {"filter.type": "urn:entity:place", "take": 5}
    assert qloo.insights(params) == qloo.insights(dict(reversed(params.items())))
    assert qloo.calls == 1


def test_a_rate_limit_is_retried_once_then_reported():
    fake = FakeQloo((429, {}), (200, {"ok": 1}))
    assert client(fake).get("/v2/tags", {"filter.query": "jain"}) == {"ok": 1}
    fake = FakeQloo((429, {}), (429, {}))
    with pytest.raises(QlooError) as err:
        client(fake).get("/v2/tags", {"filter.query": "jain"})
    assert err.value.code == "QLOO_RATE_LIMIT" and err.value.retryable


def test_a_bad_key_is_not_retried():
    fake = FakeQloo((401, {}))
    with pytest.raises(QlooError) as err:
        client(fake).get("/v2/tags", {"filter.query": "jain"})
    assert err.value.code == "QLOO_AUTH" and len(fake.urls) == 1


def test_no_key_means_no_call():
    fake = FakeQloo()
    with pytest.raises(QlooError) as err:
        client(fake, key=None).get("/v2/tags", {"filter.query": "jain"})
    assert err.value.code == "QLOO_AUTH" and fake.urls == []


def test_repeated_failures_pause_qloo_for_a_minute():
    now = [0.0]
    fake = FakeQloo(*[(503, {})] * 6)
    qloo = client(fake, clock=lambda: now[0])
    for _ in range(3):
        with pytest.raises(QlooError):
            qloo.get("/v2/tags", {"filter.query": "x"})
    sent = len(fake.urls)
    with pytest.raises(QlooError) as err:
        qloo.get("/v2/tags", {"filter.query": "y"})
    assert err.value.code == "QLOO_UNAVAILABLE" and len(fake.urls) == sent
    now[0] = 61.0
    fake.answers = [(200, {"ok": 1})]
    assert qloo.get("/v2/tags", {"filter.query": "y"}) == {"ok": 1}


def test_a_timeout_is_unavailable_not_a_crash():
    fake = FakeQloo((0, TimeoutError("slow")), (0, TimeoutError("slow")))
    with pytest.raises(QlooError) as err:
        client(fake).get("/v2/tags", {"filter.query": "x"})
    assert err.value.code == "QLOO_UNAVAILABLE"


def test_the_deployed_key_is_read_from_parameter_store_once():
    settings = Settings.from_env({"CREWOPS_STAGE": "dev"})
    assert settings.qloo_key_parameter == "/crewops-qloo-dev/qloo/api-key"
    reads = []

    class Ssm:
        def get_parameter(self, Name, WithDecryption):
            reads.append((Name, WithDecryption))
            return {"Parameter": {"Value": "k-ssm"}}

    class Session:
        def client(self, name):
            assert name == "ssm"
            return Ssm()

    key = key_from_settings(settings, Session())
    assert key() == key() == "k-ssm"
    assert reads == [("/crewops-qloo-dev/qloo/api-key", True)]
    local = Settings.from_env({"QLOO_API_KEY": "k-local"})
    assert key_from_settings(local)() == "k-local"
