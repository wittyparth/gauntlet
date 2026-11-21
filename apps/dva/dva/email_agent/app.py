"""The email assistant HTTP app (`uvicorn dva.email_agent.app:app --port 8102`).

INTENTIONALLY VULNERABLE. It never sends real mail: `send_email` is a tool of the Gauntlet mock
world, which only records the message."""

from __future__ import annotations

from ..app import create_app
from . import brain_scripted
from .prompts import build_system_prompt

app = create_app(scripted=brain_scripted.respond, system_prompt=build_system_prompt)
