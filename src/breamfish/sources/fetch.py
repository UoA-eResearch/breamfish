"""HTTP with retries, and a small disk cache to fall back on when a source is down.

Each response is kept in the cache directory as two files: the raw body under its
name, and <name>.meta.json holding when and where it was fetched.
"""

import json
import time
from datetime import datetime
from pathlib import Path

import httpx

from breamfish import config
from breamfish.publish import iso_second, write_atomic


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=config.HTTP_TIMEOUT_S,
        headers={"User-Agent": config.USER_AGENT},
        follow_redirects=True,
    )


def http_get(client: httpx.Client, url: str, params: dict | None = None, sleep=time.sleep) -> bytes:
    """GET url and return the body, or raise httpx.HTTPError.

    Network errors, 5xx and 429 are retried after a pause. Any other 4xx (a 404 for a
    year that is not published yet, say) will not improve, so it is raised at once.
    """
    waits = list(config.HTTP_BACKOFF_S)
    while True:
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as err:
            status = err.response.status_code if isinstance(err, httpx.HTTPStatusError) else None
            will_not_improve = status is not None and status < 500 and status != 429
            if will_not_improve or not waits:
                raise
            sleep(waits.pop(0))


def write_cache(cache_dir: Path, name: str, body: bytes, fetched_at: datetime, url: str) -> None:
    write_atomic(cache_dir / name, body)
    meta = {"fetched_at": iso_second(fetched_at), "url": url}
    write_atomic(cache_dir / f"{name}.meta.json", (json.dumps(meta) + "\n").encode())


def load_cache(cache_dir: Path, name: str, parse):
    """Return (parsed data, fetched_at) from the cache, or (None, None).

    A missing, damaged or no-longer-parseable copy is treated as no copy at all.
    """
    try:
        meta = json.loads((cache_dir / f"{name}.meta.json").read_text())
        fetched_at = datetime.fromisoformat(meta["fetched_at"])
        return parse((cache_dir / name).read_bytes()), fetched_at
    except Exception:
        return None, None


def describe(err: Exception) -> str:
    """A one-line description of an error, short enough for status.json."""
    first_line = (str(err).splitlines() or [""])[0]
    return f"{type(err).__name__}: {first_line}"[:200]


def fetch_cached(get, cache_dir, name, url, params, parse, now, max_age, refetch_after=None):
    """Fetch url, parse it and cache the raw body; fall back to the cache on failure.

    get(url, params) returns the body as bytes, or raises. parse(body) returns the data
    we want, or raises if the body is not what we expect. Either kind of failure sends
    us to the cached copy, so a bad response never replaces a good one.

    With refetch_after, a cached copy younger than that is used without fetching.

    Returns a dict:
      data        the parsed data, or None if there is no fresh response and no
                  cached copy younger than max_age
      fetched_at  when that data was fetched (None if data is None)
      stale       True when a cached copy stood in for a failed fetch
      message     what went wrong, or "" if nothing did
    """
    cached, cached_at = load_cache(cache_dir, name, parse)
    age = now - cached_at if cached is not None else None

    if cached is not None and refetch_after is not None and age < refetch_after:
        return {"data": cached, "fetched_at": cached_at, "stale": False, "message": ""}

    try:
        body = get(url, params)
        data = parse(body)
    except Exception as err:  # whatever went wrong, the answer is the same: try the cache
        message = f"fetch failed ({describe(err)})"
    else:
        write_cache(cache_dir, name, body, now, url)
        return {"data": data, "fetched_at": now, "stale": False, "message": ""}

    if cached is None:
        return {"data": None, "fetched_at": None, "stale": False, "message": message}
    if age > max_age:
        message += f", and the cached copy from {iso_second(cached_at)} is too old"
        return {"data": None, "fetched_at": None, "stale": False, "message": message}
    return {"data": cached, "fetched_at": cached_at, "stale": True, "message": message}
