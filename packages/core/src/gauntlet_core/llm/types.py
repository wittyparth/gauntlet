"""Result and error types of the LLM gateway."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from gauntlet_core.schema import Cost, Json


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: Json


@dataclass(frozen=True)
class LLMResult:
    text: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    parsed: BaseModel | None = None
    cost: Cost = field(default_factory=Cost)
    model: str = ""
    finish_reason: str = "stop"
    latency_ms: int = 0


class GatewayError(Exception):
    """A model call failed. `retryable` says whether trying again could help."""

    code = "gateway_error"
    retryable = False

    def __init__(
        self, message: str = "", *, code: str | None = None, retryable: bool | None = None
    ):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


class RateLimited(GatewayError):
    code = "rate_limited"
    retryable = True

    def __init__(self, message: str = "", *, retry_after_s: float | None = None, **kw):
        super().__init__(message, **kw)
        self.retry_after_s = retry_after_s


class ProviderUnavailable(GatewayError):
    code = "provider_unavailable"
    retryable = True


class AuthError(GatewayError):
    code = "auth_error"


class BadRequest(GatewayError):
    code = "bad_request"


class ContextTooLong(GatewayError):
    code = "context_too_long"


RAW_MARKER = "\n<<raw-output>>\n"
RAW_CAP = 2000


class StructuredOutputError(GatewayError):
    """The model's reply did not validate. `raw_text` is what it actually said (capped), so a
    caller can send the error back for one repair or try a lenient parse."""

    code = "structured_output_invalid"

    def __init__(self, message: str = "", *, raw_text: str = "", **kw):
        super().__init__(message, **kw)
        self.raw_text = raw_text
