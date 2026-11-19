"""Shared plumbing of the two remote targets: retry policy and wired-facade headers."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.schema import Json

from .errors import TargetError
from .facade import Facade
from .safety import UrlPolicy, check_url

__all__ = ["RemoteBase", "Timeouts", "send_with_retry"]

Sleep = Callable[[float], Awaitable[None]]
RETRY_DELAYS = (0.5, 1.0, 2.0)
RETRY_AFTER_CAP_S = 10.0


@dataclass(frozen=True)
class Timeouts:
    connect_s: float = 5.0
    read_s: float = 60.0


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return min(float(resp.headers["retry-after"]), RETRY_AFTER_CAP_S)
    except (KeyError, ValueError):
        return None


async def send_with_retry(
    client: httpx.AsyncClient,
    request: httpx.Request,
    *,
    rng: random.Random,
    sleep: Sleep,
    timeouts: Timeouts,
) -> httpx.Response:
    """Up to 3 retries on connect errors, timeouts, 429 and 5xx; other 4xx fail at once."""
    last = "no attempt"
    for attempt in range(len(RETRY_DELAYS) + 1):
        retry_after: float | None = None
        try:
            resp = await client.send(
                request,
                auth=None,
                follow_redirects=False,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last = f"{type(e).__name__}: {e}"
        else:
            if resp.status_code < 400:
                return resp
            body = resp.text[:200]
            if resp.status_code != 429 and resp.status_code < 500:
                raise TargetError(f"http_{resp.status_code}", body)
            last, retry_after = f"http {resp.status_code}: {body}", _retry_after(resp)
        if attempt < len(RETRY_DELAYS):
            delay = RETRY_DELAYS[attempt] * (1 + rng.uniform(-0.2, 0.2))
            await sleep(retry_after if retry_after is not None else delay)
    raise TargetError("unreachable", last)


class RemoteBase:
    """Holds what both remote targets need: client, URL policy, facade and retry settings."""

    stateful = False

    def __init__(
        self,
        *,
        secrets: Mapping[str, str],
        client: httpx.AsyncClient,
        facade: Facade | None,
        safety: UrlPolicy,
        wired: bool,
        timeouts: Timeouts = Timeouts(),
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._secrets, self._client, self._facade = secrets, client, facade
        self._safety, self._wired = safety, wired
        self._timeouts, self._sleep = timeouts, sleep
        self._token: str | None = None
        self.history: list[Json] = []

    async def open(self, ctx: EpisodeCtx) -> None:
        self.history = []
        if self._wired and self._facade is not None:
            self._token = self._facade.attach(ctx, ctx.state["world"])

    async def close(self, ctx: EpisodeCtx) -> None:
        if self._token is not None and self._facade is not None:
            self._facade.detach(self._token)
            self._token = None

    def wired_headers(self) -> dict[str, str]:
        if self._token is None or self._facade is None:
            return {}
        return {"X-Gauntlet-Episode": self._token, "X-Gauntlet-Mock-Base": self._facade.base_url}

    async def call(
        self, ctx: EpisodeCtx, turn: int, method: str, url: str, **kw: Any
    ) -> httpx.Response:
        check_url(url, self._safety)
        request = self._client.build_request(
            method,
            url,
            timeout=httpx.Timeout(self._timeouts.read_s, connect=self._timeouts.connect_s),
            **kw,
        )
        rng = random.Random(f"{ctx.rng_seed}:{turn}")
        return await send_with_retry(
            self._client, request, rng=rng, sleep=self._sleep, timeouts=self._timeouts
        )
