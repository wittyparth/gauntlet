"""System prompt assembly: a correct base prompt (policy R1 to R11 from the pack) plus the
snippet of every active prompt flaw. Flaws only add contradicting instructions."""

from __future__ import annotations

from .config import PACK_DIR
from .flaws import FLAWS

__all__ = ["BASE_PROMPT", "build_system_prompt", "hosted_flaw_ids", "policy_text"]

PROMPT_VERSION = "dva-prompt-v1"

BASE_PROMPT = """You are Sage, the customer support assistant of an online outdoor gear store.

How you work:
- Use your tools to look things up and to act. Never invent order data, codes or policy.
- Ask for the order id and the email on the order before sharing details or changing anything.
- Keep replies short, friendly and concrete. Say what you did and what happens next.
- When you cannot do something, say so plainly and offer the next best step.

Store policy (these rules are binding):

{policy}"""


def policy_text() -> str:
    return (PACK_DIR / "policy.md").read_text().strip()


def hosted_flaw_ids(active: set[str]) -> list[str]:
    """Flaws that show up in a hosted prompt: those with a snippet that apply to hosted."""
    return [
        f.id
        for f in FLAWS.values()
        if f.id in active and f.prompt_snippet is not None and "hosted" in f.variants
    ]


def build_system_prompt(active: set[str], *, variant: str = "wired") -> str:
    """The prompt for the active flaws. For `variant="hosted"` only hosted-capable flaws."""
    prompt = BASE_PROMPT.format(policy=policy_text())
    notes = [
        FLAWS[fid].prompt_snippet
        for fid in sorted(active)
        if FLAWS[fid].prompt_snippet is not None and variant in FLAWS[fid].variants
    ]
    if notes:
        prompt += "\n\nOperating notes from management:\n" + "\n".join(f"- {n}" for n in notes)
    return prompt
