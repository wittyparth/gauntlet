"""LLM gateway (P1-1). Episode code calls models only through `llm_effect`."""

from .config import (
    GatewayConfig,
    LlmSection,
    PricingConfig,
    RateLimitConfig,
    RoleConfig,
    load_config,
)
from .effects import llm_effect
from .embed import HashEmbedder, cosine
from .fake import CallRecord, FakeLLM, FakeReply
from .gateway import Gateway
from .litellm_gateway import LiteLLMGateway
from .ratelimit import LocalRateLimiter, ProviderLimiter, RateLimiter, build_limiter
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

__all__ = [
    "AuthError",
    "BadRequest",
    "CallRecord",
    "ContextTooLong",
    "FakeLLM",
    "FakeReply",
    "Gateway",
    "GatewayConfig",
    "GatewayError",
    "HashEmbedder",
    "LLMResult",
    "LiteLLMGateway",
    "LlmSection",
    "LocalRateLimiter",
    "PricingConfig",
    "ProviderLimiter",
    "ProviderUnavailable",
    "RateLimitConfig",
    "RateLimited",
    "RateLimiter",
    "RoleConfig",
    "StructuredOutputError",
    "ToolCallRequest",
    "build_limiter",
    "cosine",
    "llm_effect",
    "load_config",
]
