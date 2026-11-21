"""DVA settings, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DEFAULT_MODEL", "PACK_DIR", "WORLDS_DIR", "Settings", "load_settings", "world_file"]

DEFAULT_MODEL = "openrouter/deepseek/deepseek-v4-flash"
PACK_DIR = Path(os.environ.get("DVA_PACK_DIR", Path(__file__).parents[3] / "packs" / "ecommerce"))


@dataclass(frozen=True)
class Settings:
    brain: str = "llm"  # "llm" or "scripted"
    model: str = DEFAULT_MODEL
    mock_base: str = "http://127.0.0.1:8000"
    host: str = "127.0.0.1"
    port: int = 8100
    world: str = "unfixed"  # unfixed | fixed: which world file the platform pairs with this agent


def load_settings() -> Settings:
    env = os.environ
    brain = env.get("DVA_BRAIN", "llm")
    if brain not in ("llm", "scripted"):
        raise ValueError(f"DVA_BRAIN must be llm or scripted, got {brain!r}")
    if env.get("DVA_WORLD", "unfixed") not in ("unfixed", "fixed"):
        raise ValueError("DVA_WORLD must be unfixed or fixed")
    return Settings(
        brain=brain,
        model=env.get("DVA_MODEL", DEFAULT_MODEL),
        mock_base=env.get("GAUNTLET_MOCK_BASE", Settings.mock_base),
        host=env.get("DVA_HOST", Settings.host),
        port=int(env.get("DVA_PORT", Settings.port)),
        world=env.get("DVA_WORLD", "unfixed"),
    )


WORLDS_DIR = Path(__file__).parents[1] / "worlds"


def world_file(agent: str, world: str = "unfixed") -> Path:
    """The world YAML the platform pairs with `agent` (`sql` or `email`) for `DVA_WORLD`."""
    return WORLDS_DIR / f"{agent}{'_fixed' if world == 'fixed' else ''}.yaml"
