"""Targets: how Gauntlet talks to the agent under test (hosted, OpenAI-compatible, HTTP)."""

from .errors import TargetError
from .facade import Facade, LocalFacade
from .hosted import HostedTarget
from .http import HttpTarget, render_template
from .jsonpath import MISSING, get_path, set_path
from .openai_compat import OpenAICompatTarget
from .remote import Timeouts
from .safety import GuardedTransport, UrlPolicy, check_url
from .tokens import mint_token, verify_token

__all__ = [
    "MISSING",
    "Facade",
    "GuardedTransport",
    "HostedTarget",
    "HttpTarget",
    "LocalFacade",
    "OpenAICompatTarget",
    "TargetError",
    "Timeouts",
    "UrlPolicy",
    "check_url",
    "get_path",
    "mint_token",
    "render_template",
    "set_path",
    "verify_token",
]
