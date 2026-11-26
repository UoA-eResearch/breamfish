import json
from datetime import timedelta

import httpx
import pytest
from conftest import NOW

from breamfish import config
from breamfish.sources import fetch

URL = "https://example.invalid/data"
HOUR = timedelta(hours=1)


def parse(body: bytes):
    """A stand-in parser: accepts JSON objects with a "value", rejects anything else."""
    return json.loads(body)["value"]


def fetch_once(get, cache_dir, now, **options):
    options.setdefault("max_age", 12 * HOUR)
    return fetch.fetch_cached(get, cache_dir, "thing.json", URL, None, parse, now, **options)


def returning(body: bytes, calls: list | None = None):
    def get(url, params=None):
        if calls is not None:
            calls.append(url)
        return body

    return get


def failing(url, params=None):
    raise httpx.ConnectError("connection refused")


# --- cache --------------------------------------------------------------------------


def test_fresh_fetch_is_cached_with_its_fetch_time(tmp_path):
    result = fetch_once(returning(b'{"value": 1}'), tmp_path, NOW)

    assert result == {"data": 1, "fetched_at": NOW, "stale": False, "message": ""}
    assert (tmp_path / "thing.json").read_bytes() == b'{"value": 1}'
    meta = json.loads((tmp_path / "thing.json.meta.json").read_text())
    assert meta == {"fetched_at": "2026-11-26T04:05:12Z", "url": URL}


def test_falls_back_to_the_cache_when_the_fetch_raises(tmp_path):
    fetch_once(returning(b'{"value": 1}'), tmp_path, NOW)

    result = fetch_once(failing, tmp_path, NOW + 11 * HOUR)

    assert result["data"] == 1
    assert result["stale"] is True
    assert result["fetched_at"] == NOW
    assert result["message"] == "fetch failed (ConnectError: connection refused)"


def test_cached_copy_older_than_max_age_is_not_used(tmp_path):
    fetch_once(returning(b'{"value": 1}'), tmp_path, NOW)

    result = fetch_once(failing, tmp_path, NOW + 13 * HOUR)

    assert result["data"] is None
    assert result["fetched_at"] is None
    assert "too old" in result["message"]


def test_no_cache_and_no_fetch_gives_nothing(tmp_path):
    result = fetch_once(failing, tmp_path, NOW)

    assert result["data"] is None
    assert result["stale"] is False
    assert result["message"].startswith("fetch failed")


def test_a_bad_response_does_not_replace_a_good_cached_one(tmp_path):
    fetch_once(returning(b'{"value": 1}'), tmp_path, NOW)

    result = fetch_once(returning(b"<html>502 Bad Gateway</html>"), tmp_path, NOW + HOUR)

    assert result["data"] == 1
    assert result["stale"] is True
    assert (tmp_path / "thing.json").read_bytes() == b'{"value": 1}'


def test_a_damaged_cache_counts_as_no_cache(tmp_path):
    fetch_once(returning(b'{"value": 1}'), tmp_path, NOW)
    (tmp_path / "thing.json").write_bytes(b"\x00\x00")

    assert fetch_once(failing, tmp_path, NOW + HOUR)["data"] is None
    assert fetch_once(returning(b'{"value": 2}'), tmp_path, NOW + HOUR)["data"] == 2


def test_refetch_after_skips_the_request_while_the_copy_is_young(tmp_path):
    calls = []
    get = returning(b'{"value": 1}', calls)

    fetch_once(get, tmp_path, NOW, refetch_after=7 * 24 * HOUR)
    young = fetch_once(get, tmp_path, NOW + 24 * HOUR, refetch_after=7 * 24 * HOUR)
    assert len(calls) == 1
    assert young == {"data": 1, "fetched_at": NOW, "stale": False, "message": ""}

    fetch_once(get, tmp_path, NOW + 8 * 24 * HOUR, refetch_after=7 * 24 * HOUR)
    assert len(calls) == 2


# --- HTTP ---------------------------------------------------------------------------


def client_answering(handler) -> httpx.Client:
    """An httpx client wired to a function, not to the network."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_user_agent_names_the_project_and_nothing_personal():
    with fetch.make_client() as client:
        agent = client.headers["User-Agent"]
        assert client.timeout == httpx.Timeout(30)
    assert agent.startswith("breamfish/")
    assert agent.endswith("(+https://github.com/UoA-eResearch/breamfish)")


def test_two_retries_with_a_pause_before_each():
    attempts, pauses = [], []

    def handler(request):
        attempts.append(request.url)
        if len(attempts) < 3:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, content=b"body")

    with client_answering(handler) as client:
        body = fetch.http_get(client, URL, {"a": "1,2"}, sleep=pauses.append)

    assert body == b"body"
    assert len(attempts) == 3
    assert pauses == list(config.HTTP_BACKOFF_S)


def test_gives_up_after_the_second_retry():
    attempts = []

    def handler(request):
        attempts.append(request.url)
        return httpx.Response(503)

    with client_answering(handler) as client, pytest.raises(httpx.HTTPStatusError):
        fetch.http_get(client, URL, sleep=lambda seconds: None)
    assert len(attempts) == 3


def test_a_404_is_not_retried():
    attempts = []

    def handler(request):
        attempts.append(request.url)
        return httpx.Response(404)

    with client_answering(handler) as client, pytest.raises(httpx.HTTPStatusError):
        fetch.http_get(client, URL, sleep=lambda seconds: None)
    assert len(attempts) == 1
