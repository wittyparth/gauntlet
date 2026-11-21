"""The SQL agent HTTP app (`uvicorn dva.sql_agent.app:app --port 8101`).

INTENTIONALLY VULNERABLE. It only ever talks to the mock world's in-memory database through
the Gauntlet tool facade; it has no database connection of its own."""

from __future__ import annotations

from ..app import create_app
from . import brain_scripted
from .prompts import build_system_prompt

app = create_app(scripted=brain_scripted.respond, system_prompt=build_system_prompt)
