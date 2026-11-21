"""README badges (P3-4, CQ-R9). The public endpoint exposes one short string and nothing else:
a pass rate with its interval, or the security grade letter. The SVG comes from a fixed template
and every dynamic piece is restricted to a tiny alphabet before it is written."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Agent, AgentVersion, Run
from ..db.review_models import BadgeToken
from ..errors import not_found
from .audit import audit
from .posture import _observed, build_posture
from .reports import run_report

__all__ = [
    "BadgeOut",
    "Metric",
    "Rendered",
    "create_or_rotate",
    "etag_of",
    "render_svg",
    "resolve_badge",
]

Metric = Literal["pass_rate", "security"]
GREEN, AMBER, RED, GREY = "#3fa34d", "#d4a017", "#c9433b", "#8a8f98"
ALLOWED = re.compile(r"[^0-9A-Za-z%± ]")
GRADE_COLOUR = {"A": GREEN, "B": GREEN, "C": AMBER, "D": RED, "F": RED}


class BadgeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    url: str
    markdown: str


class Rendered(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    value: str
    colour: str


def colour_for(rate: float | None) -> str:
    if rate is None:
        return GREY
    return GREEN if rate >= 0.90 else AMBER if rate >= 0.75 else RED


def clean(text: str) -> str:
    """Only digits, letters, `%`, the plus-minus sign and spaces survive."""
    return ALLOWED.sub("", text)[:24]


def render_svg(label: str, value: str, colour: str) -> str:
    label, value = clean(label), clean(value)
    lw = round(6.5 * len(label) + 10)
    vw = round(6.5 * len(value) + 10)
    total = lw + vw
    text_y = 14
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" '
        f'aria-label="{label}: {value}">'
        f'<rect width="{lw}" height="20" fill="#555"/>'
        f'<rect x="{lw}" width="{vw}" height="20" fill="{colour}"/>'
        f'<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11" '
        f'text-anchor="middle">'
        f'<text x="{lw / 2}" y="{text_y}">{label}</text>'
        f'<text x="{lw + vw / 2}" y="{text_y}">{value}</text></g></svg>'
    )


def etag_of(svg: str) -> str:
    return '"' + hashlib.sha256(svg.encode()).hexdigest()[:20] + '"'


def new_token() -> str:
    return "gb_" + secrets.token_urlsafe(24)


async def create_or_rotate(
    s: AsyncSession, ws: str, agent_id: str, public_url: str, actor: str
) -> BadgeOut:
    from gauntlet_core.ids import new_id

    agent = await s.get(Agent, agent_id)
    if agent is None or agent.workspace_id != ws:
        raise not_found("agent", agent_id)
    await s.execute(
        update(BadgeToken)
        .where(BadgeToken.agent_id == agent_id, BadgeToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    token = new_token()
    s.add(BadgeToken(id=new_id("bdg"), workspace_id=ws, agent_id=agent_id, token=token))
    await audit(s, ws, actor, "badge.rotated", "agent", agent_id, {})
    await s.commit()
    url = f"{public_url.rstrip('/')}/badge/{token}.svg"
    return BadgeOut(token=token, url=url, markdown=f"![gauntlet]({url})")


async def _newest_version(s: AsyncSession, agent_id: str) -> str | None:
    return (
        await s.execute(
            select(AgentVersion.id)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.created_at.desc(), AgentVersion.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def resolve_badge(s: AsyncSession, token: str, metric: Metric) -> Rendered | None:
    """None for an unknown or revoked token (the caller answers 404 with an `invalid` badge)."""
    row = (
        await s.execute(select(BadgeToken).where(BadgeToken.token == token))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    vid = await _newest_version(s, row.agent_id)
    label = "gauntlet" if metric == "pass_rate" else "security"
    if vid is None:
        return Rendered(label=label, value="no data", colour=GREY)
    if metric == "security":
        if not await _observed(s, vid):
            return Rendered(label=label, value="no data", colour=GREY)
        grade = str((await build_posture(s, row.workspace_id, row.agent_id, vid))["grade"])
        return Rendered(label=label, value=grade, colour=GRADE_COLOUR.get(grade, GREY))
    run = (
        await s.execute(
            select(Run)
            .where(Run.agent_version_id == vid, Run.status == "done", Run.purpose == "eval")
            .order_by(Run.created_at.desc(), Run.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None:
        return Rendered(label=label, value="no data", colour=GREY)
    rep = await run_report(s, run)
    if rep.pass_rate is None or rep.ci_low is None or rep.ci_high is None:
        return Rendered(label=label, value="no data", colour=GREY)
    half = round((rep.ci_high - rep.ci_low) / 2 * 100)
    return Rendered(
        label=label,
        value=f"{round(rep.pass_rate * 100)}% ±{half}",
        colour=colour_for(rep.pass_rate),
    )
