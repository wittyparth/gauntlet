"""Structured-output robustness: one repair retry, then a lenient parse, then fail loudly.

Cheap models sometimes return an empty reply, truncated JSON or JSON wrapped in prose. The
gateway makes a single attempt and raises `StructuredOutputError` carrying the raw text; this
module owns the recovery so that, inside an episode, every attempt is its own journaled `llm`
effect (replay re-derives the same recovery path with zero model calls):

1. the call; 2. on invalid output, one repair call that sends the validation error back;
3. on a second failure, a lenient parse of what the model said (the caller supplies it, and it
   must be deterministic); 4. only then the original error is raised.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ValidationError

from gauntlet_core.engine import EpisodeCtx, PermanentEffectError
from gauntlet_core.llm.effects import llm_effect
from gauntlet_core.llm.gateway import Gateway
from gauntlet_core.llm.types import (
    RAW_MARKER,
    GatewayError,
    LLMResult,
    StructuredOutputError,
)
from gauntlet_core.schema import Json

__all__ = [
    "REPAIR_PROMPT_VERSION",
    "Lenient",
    "extract_json_object",
    "lenient_json",
    "repair_messages",
    "structured_call",
    "structured_effect",
]

REPAIR_PROMPT_VERSION = "structured-repair/1"
INVALID_CODE = StructuredOutputError.code
Lenient = Callable[[str], BaseModel | None]

_REPAIR = (
    "Your previous reply could not be used: {error}\n"
    "Reply again with exactly one complete JSON object that matches the required schema. "
    "No markdown code fences, no text before or after it, and keep every string short enough "
    "that the object is finished."
)
_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def _short_error(error: str) -> str:
    first = error.strip().splitlines()[0] if error.strip() else "empty reply"
    if "Invalid JSON" in error or "json_invalid" in error:
        first = "the reply was empty or not valid JSON (possibly cut off)"
    return first[:300]


def repair_messages(messages: list[Json], raw: str, error: str) -> list[Json]:
    """The original conversation, the bad reply (when there was one), and the error."""
    out = list(messages)
    if raw.strip():
        out.append({"role": "assistant", "content": raw})
    out.append({"role": "user", "content": _REPAIR.format(error=_short_error(error))})
    return out


def _invalid(e: Exception) -> tuple[str, str] | None:
    """(raw reply, validation error) when `e` is an invalid-structured-output failure."""
    if isinstance(e, StructuredOutputError):
        return e.raw_text, e.message
    if isinstance(e, PermanentEffectError | GatewayError) and e.code == INVALID_CODE:
        error, _, raw = e.message.partition(RAW_MARKER)
        return raw, error
    return None


def extract_json_object(text: str) -> Json | None:
    """The first JSON object found in plain text: the whole text, a fenced block, or the first
    balanced `{...}` span. None when there is none."""
    candidates = [text.strip(), *(m.strip() for m in _FENCE.findall(text))]
    start = text.find("{")
    while start != -1 and start < len(text):
        end = _balanced_end(text, start)
        if end is not None:
            candidates.append(text[start : end + 1])
        start = text.find("{", start + 1)
    for c in candidates:
        try:
            value = json.loads(c)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _balanced_end(text: str, start: int) -> int | None:
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def lenient_json(model: type[BaseModel]) -> Lenient:
    """Lenient parser: JSON found in fences or prose, validated against `model`."""

    def parse(text: str) -> BaseModel | None:
        obj = extract_json_object(text)
        if obj is None:
            return None
        try:
            return model.model_validate(obj)
        except ValidationError:
            return None

    return parse


async def structured_call(
    call: Callable[[list[Json]], Awaitable[LLMResult]],
    messages: list[Json],
    *,
    lenient: Lenient | None = None,
) -> LLMResult:
    """Run `call(messages)`; on invalid structured output make one repair call, then fall back
    to `lenient(raw)` over the second then the first raw reply; else re-raise the failure."""
    try:
        return await call(messages)
    except (GatewayError, PermanentEffectError) as first:
        bad = _invalid(first)
        if bad is None:
            raise
        raw1, err1 = bad
    try:
        return await call(repair_messages(messages, raw1, err1))
    except (GatewayError, PermanentEffectError) as second:
        bad2 = _invalid(second)
        if bad2 is None:
            raise
        raw2, _ = bad2
        if lenient is not None:
            for raw in (raw2, raw1):
                parsed = lenient(raw) if raw.strip() else None
                if parsed is not None:
                    return LLMResult(text=raw, parsed=parsed, finish_reason="lenient_parse")
        raise


async def structured_effect(
    ctx: EpisodeCtx,
    gateway: Gateway,
    role: str,
    messages: list[Json],
    *,
    response_model: type[BaseModel],
    lenient: Lenient | None = None,
    temperature: float | None = None,
    seed: int | None = None,
    error_cls: type[PermanentEffectError] = PermanentEffectError,
) -> LLMResult:
    """`llm_effect` with `structured_call` recovery; each attempt is its own effect."""

    async def call(msgs: list[Json]) -> LLMResult:
        return await llm_effect(
            ctx,
            gateway,
            role,
            msgs,
            response_model=response_model,
            temperature=temperature,
            seed=seed,
            error_cls=error_cls,
        )

    return await structured_call(call, messages, lenient=lenient)
