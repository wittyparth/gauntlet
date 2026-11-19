"""LiteLLM-backed Gateway: retries, fallbacks, structured output repair, cost accounting."""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import litellm
import litellm.exceptions as lx
from pydantic import BaseModel, ValidationError

from gauntlet_core.schema import Cost, Json

from .config import GatewayConfig, RoleConfig
from .embed import HashEmbedder
from .pricing import (
    cost_from_pricing,
    estimate_micros,
    litellm_token_prices,
    make_cost,
    to_micros,
)
from .ratelimit import RateLimiter, build_limiter
from .types import (
    AuthError,
    BadRequest,
    ContextTooLong,
    GatewayError,
    LLMResult,
    ProviderUnavailable,
    RateLimited,
    StructuredOutputError,
    ToolCallRequest,
)

_REPAIR = "Your previous output was invalid: {error}. Return only valid JSON for the schema."


def map_exception(exc: Exception) -> GatewayError:
    """Translate a litellm / openai exception into a GatewayError."""
    if isinstance(exc, GatewayError):
        return exc
    msg = str(exc)
    if isinstance(exc, lx.ContextWindowExceededError):
        return ContextTooLong(msg)
    if isinstance(exc, lx.RateLimitError):
        retry_after = None
        headers = getattr(getattr(exc, "response", None), "headers", None)
        if headers is not None:
            try:
                retry_after = float(headers.get("retry-after"))
            except (TypeError, ValueError):
                retry_after = None
        return RateLimited(msg, retry_after_s=retry_after)
    if isinstance(exc, lx.AuthenticationError | lx.PermissionDeniedError):
        return AuthError(msg)
    if isinstance(
        exc,
        lx.Timeout
        | lx.APIConnectionError
        | lx.ServiceUnavailableError
        | lx.InternalServerError
        | lx.BadGatewayError,
    ):
        return ProviderUnavailable(msg)
    if isinstance(exc, lx.BadRequestError):
        return BadRequest(msg)
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status >= 500:
        return ProviderUnavailable(msg)
    return BadRequest(msg)


def provider_of(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else "default"


class LiteLLMGateway:
    def __init__(
        self,
        config: GatewayConfig,
        *,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self.config = config
        self.limiter = limiter or build_limiter(config)
        self._sleep, self._jitter = sleep, jitter
        self.unpriced_models: set[str] = set()
        self._hash = HashEmbedder()

    # ------------------------------------------------------------------ roles

    def _resolve(self, role: str) -> RoleConfig:
        if role.startswith("model:"):
            return RoleConfig(model=role[len("model:") :])
        try:
            return self.config.llm.roles[role]
        except KeyError:
            raise BadRequest(f"unknown role {role!r}") from None

    # ------------------------------------------------------------------ cost

    def _cost(self, model: str, resp: Any, in_tok: int, out_tok: int) -> Cost:
        price = self.config.llm.pricing.get(model)
        if price is not None:
            return make_cost(model, cost_from_pricing(price, in_tok, out_tok), in_tok, out_tok)
        try:
            usd = float(litellm.completion_cost(completion_response=resp))
        except Exception:
            usd = 0.0
        if usd <= 0:
            self.unpriced_models.add(model)
            return make_cost(model, 0, in_tok, out_tok)
        return make_cost(model, to_micros(usd), in_tok, out_tok)

    def estimate_usd_micros(
        self, role: str, messages: list[Json], *, max_output_tokens: int | None = None
    ) -> int:
        rc = self._resolve(role)
        try:
            in_tok = int(litellm.token_counter(model=rc.model, messages=messages))
        except Exception:
            in_tok = sum(len(json.dumps(m)) for m in messages) // 4
        return estimate_micros(
            self.config.llm.pricing,
            rc.model,
            in_tok,
            max_output_tokens or rc.max_output_tokens,
            litellm_token_prices(rc.model),
        )

    # ------------------------------------------------------------------ calls

    async def _attempt(
        self,
        model: str,
        rc: RoleConfig,
        messages: list[Json],
        tools: list[Json] | None,
        response_format: Json | None,
        temperature: float | None,
        seed: int | None,
    ) -> Any:
        est_tokens = sum(len(json.dumps(m)) for m in messages) // 4 + rc.max_output_tokens
        await self.limiter.acquire(provider_of(model), est_tokens)
        kwargs: Json = {
            "model": model,
            "messages": messages,
            "max_tokens": rc.max_output_tokens,
            "timeout": self.config.llm.request_timeout_s,
            "drop_params": True,  # providers that reject temperature/seed ignore them
            "num_retries": 0,  # retries are ours
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if seed is not None:
            kwargs["seed"] = seed
        if tools:
            kwargs["tools"] = tools
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            return await litellm.acompletion(**kwargs)
        except Exception as e:
            raise map_exception(e) from e

    async def _with_retries(self, rc: RoleConfig, **kw: Any) -> tuple[Any, str]:
        cfg = self.config.llm
        last: GatewayError | None = None
        for model in [rc.model, *rc.fallbacks]:
            for n in range(cfg.max_attempts):
                try:
                    return await self._attempt(model, rc, **kw), model
                except GatewayError as e:
                    if not e.retryable:
                        raise
                    last = e
                    if n == cfg.max_attempts - 1:
                        break
                    delay = min(20.0, cfg.backoff_base_s * 2**n) * self._jitter()
                    if isinstance(e, RateLimited) and e.retry_after_s:
                        delay = max(delay, e.retry_after_s)
                    await self._sleep(delay)
        assert last is not None
        raise last

    @staticmethod
    def _extract(resp: Any) -> tuple[str, list[ToolCallRequest], str, int, int]:
        choice = resp.choices[0]
        msg = choice.message
        calls = []
        for tc in getattr(msg, "tool_calls", None) or []:
            raw = tc.function.arguments
            try:
                args = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
            except json.JSONDecodeError:
                args = {"_raw": raw}
            calls.append(ToolCallRequest(id=tc.id, name=tc.function.name, arguments=args))
        usage = getattr(resp, "usage", None)
        in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
        out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
        return (
            msg.content or "",
            calls,
            choice.finish_reason or "stop",
            in_tok,
            out_tok,
        )

    async def complete(
        self,
        role: str,
        messages: list[Json],
        *,
        tools: list[Json] | None = None,
        response_model: type[BaseModel] | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> LLMResult:
        rc = self._resolve(role)
        temp = temperature if temperature is not None else rc.temperature
        fmt: Json | None = None
        if response_model is not None:
            fmt = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": response_model.model_json_schema(),
                    "strict": True,
                },
            }
        started = time.perf_counter()
        total = Cost()
        convo = list(messages)
        parsed: BaseModel | None = None
        for repair in (False, True):
            resp, model = await self._with_retries(
                rc,
                messages=convo,
                tools=tools,
                response_format=fmt,
                temperature=temp,
                seed=seed,
            )
            text, calls, finish, in_tok, out_tok = self._extract(resp)
            total = total + self._cost(model, resp, in_tok, out_tok)
            if response_model is None:
                break
            try:
                parsed = response_model.model_validate_json(text)
                break
            except ValidationError as e:
                if repair:
                    raise StructuredOutputError(str(e)) from e
                convo = [
                    *convo,
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": _REPAIR.format(error=e)},
                ]
        return LLMResult(
            text=text,
            tool_calls=calls,
            parsed=parsed,
            cost=total,
            model=model,
            finish_reason=finish,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def embed(self, role: str, texts: list[str]) -> list[list[float]]:
        rc = self._resolve(role)
        if rc.model == "hash":
            return self._hash.embed(texts)
        try:
            resp = await litellm.aembedding(model=rc.model, input=texts)
        except Exception as e:
            raise map_exception(e) from e
        return [list(d["embedding"]) for d in resp.data]
