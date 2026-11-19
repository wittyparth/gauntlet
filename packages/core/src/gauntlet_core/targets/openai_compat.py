"""Target for any OpenAI-compatible `/chat/completions` endpoint."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.schema import Cost, Json, OpenAICompatTargetConfig

from .errors import TargetError
from .facade import Facade
from .remote import RemoteBase, Sleep, Timeouts
from .safety import UrlPolicy

__all__ = ["OpenAICompatTarget"]


class OpenAICompatTarget(RemoteBase):
    stateful = False

    def __init__(
        self,
        config: OpenAICompatTargetConfig,
        *,
        secrets: Mapping[str, str],
        client: httpx.AsyncClient,
        safety: UrlPolicy,
        facade: Facade | None = None,
        timeouts: Timeouts | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        extra: dict[str, Any] = {}
        if sleep is not None:
            extra["sleep"] = sleep
        super().__init__(
            secrets=secrets,
            client=client,
            facade=facade,
            safety=safety,
            wired=config.wired,
            timeouts=timeouts or Timeouts(),
            **extra,
        )
        self.config = config

    def _headers(self) -> dict[str, str]:
        headers = self.wired_headers()
        name = self.config.api_key_secret
        if name:
            if name not in self._secrets:
                raise TargetError("missing_secret", name)
            headers["Authorization"] = f"Bearer {self._secrets[name]}"
        return headers

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        turn = len(self.history) // 2
        self.history.append({"role": "user", "content": user_text})
        messages = [dict(m) for m in self.history]
        headers = self._headers()
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        body = {"model": self.config.model, "messages": messages, "temperature": 0}

        async def fn() -> tuple[Json, Cost | None]:
            resp = await self.call(ctx, turn, "POST", url, json=body, headers=headers)
            try:
                content = resp.json()["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError):
                content = None
            if not isinstance(content, str):
                raise TargetError("bad_reply", "missing choices[0].message.content")
            return {"reply": content}, None

        res = await ctx.effect(
            "target",
            {"turn": turn, "messages": messages},
            fn,
            retry_safe=True,
            nested=self._wired,
        )
        reply = str(res["reply"])
        self.history.append({"role": "assistant", "content": reply})
        return reply
