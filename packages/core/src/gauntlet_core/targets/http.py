"""Target for an arbitrary JSON-over-HTTP agent described by a body template."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import httpx

from gauntlet_core.engine import EpisodeCtx
from gauntlet_core.schema import Cost, HttpTargetConfig, Json

from .errors import TargetError
from .facade import Facade
from .jsonpath import MISSING, get_path
from .remote import RemoteBase, Sleep, Timeouts
from .safety import UrlPolicy

__all__ = ["HttpTarget", "render_template"]

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
_SECRET = re.compile(r"\{\{\s*secret:([A-Za-z0-9_.-]+)\s*\}\}")
_METHODS = {"POST", "PUT", "GET"}


def render_template(template: Any, values: Mapping[str, Any]) -> Any:
    """Replace placeholders. A string that is exactly one placeholder takes the raw value
    (types preserved); otherwise values are substituted into the string as text."""
    if isinstance(template, dict):
        return {k: render_template(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [render_template(v, values) for v in template]
    if not isinstance(template, str):
        return template
    whole = _PLACEHOLDER.fullmatch(template.strip())
    if whole and whole.group(1) in values:
        return values[whole.group(1)]

    def sub(m: re.Match[str]) -> str:
        v = values.get(m.group(1), m.group(0))
        return v if isinstance(v, str) else json.dumps(v)

    return _PLACEHOLDER.sub(sub, template)


class HttpTarget(RemoteBase):
    def __init__(
        self,
        config: HttpTargetConfig,
        *,
        secrets: Mapping[str, str],
        client: httpx.AsyncClient,
        safety: UrlPolicy,
        facade: Facade | None = None,
        timeouts: Timeouts | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        method = config.method.upper()
        if method not in _METHODS:
            raise ValueError(f"unsupported method {config.method!r}; use POST, PUT or GET")
        extra: dict[str, Any] = {"sleep": sleep} if sleep is not None else {}
        super().__init__(
            secrets=secrets,
            client=client,
            facade=facade,
            safety=safety,
            wired=config.wired,
            timeouts=timeouts or Timeouts(),
            **extra,
        )
        self.config, self.method = config, method
        self.stateful = config.stateful
        self.conversation_id: str | None = None

    def _headers(self) -> dict[str, str]:
        def sub(m: re.Match[str]) -> str:
            if m.group(1) not in self._secrets:
                raise TargetError("missing_secret", m.group(1))
            return self._secrets[m.group(1)]

        out = {k: _SECRET.sub(sub, v) for k, v in self.config.headers.items()}
        return {**out, **self.wired_headers()}

    async def open(self, ctx: EpisodeCtx) -> None:
        await super().open(ctx)
        self.conversation_id = None

    async def send(self, ctx: EpisodeCtx, user_text: str) -> str:
        cfg = self.config
        turn = len(self.history) // 2
        values = {
            "message": user_text,
            "conversation_id": self.conversation_id or "",
            "history": [dict(m) for m in self.history],  # prior turns, current excluded
        }
        body = render_template(cfg.body_template, values)
        headers = self._headers()
        self.history.append({"role": "user", "content": user_text})
        kw: dict[str, Any] = {"headers": headers}
        kw["params" if self.method == "GET" else "json"] = body

        async def fn() -> tuple[Json, Cost | None]:
            resp = await self.call(ctx, turn, self.method, cfg.url, **kw)
            try:
                data = resp.json()
            except ValueError as e:
                raise TargetError("bad_reply", "response is not JSON") from e
            reply = get_path(data, cfg.reply_path)
            if reply is MISSING or not isinstance(reply, str):
                raise TargetError("bad_reply", f"no string at {cfg.reply_path}")
            out: Json = {"reply": reply, "conversation_id": None}
            if cfg.conversation_id_path:
                cid = get_path(data, cfg.conversation_id_path)
                out["conversation_id"] = None if cid is MISSING else str(cid)
            return out, None

        res = await ctx.effect(
            "target",
            {"turn": turn, "body": body, "conversation_id": self.conversation_id},
            fn,
            retry_safe=not cfg.stateful,
            nested=self._wired,
        )
        if res.get("conversation_id"):
            self.conversation_id = str(res["conversation_id"])
        reply = str(res["reply"])
        self.history.append({"role": "assistant", "content": reply})
        return reply
