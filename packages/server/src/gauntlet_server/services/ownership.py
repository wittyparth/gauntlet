"""Ownership verification of remote targets (P2-4). A non-local target must be proven to belong
to the workspace (DNS TXT record or an HTTPS well-known file) before attack runs may use it."""

from __future__ import annotations

import ipaddress
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import dns.asyncresolver
import dns.exception
import httpx
import tldextract
from gauntlet_core.ids import new_id
from gauntlet_core.schema import TargetConfig
from gauntlet_core.targets import GuardedTransport, TargetError, UrlPolicy
from gauntlet_core.targets.safety import resolve_host
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.sec_models import TargetVerification
from ..errors import ApiError

__all__ = [
    "DEPS",
    "check_verification",
    "covering_verification",
    "instructions",
    "is_remote",
    "normalise_host",
    "request_verification",
    "require_target_verified",
    "target_host",
]

CHALLENGE_LABEL = "_gauntlet-challenge"
WELL_KNOWN = "/.well-known/gauntlet-challenge.txt"
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)  # bundled snapshot


async def _dns_txt(name: str) -> list[str]:
    resolver = dns.asyncresolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 10
    try:
        answer = await resolver.resolve(name, "TXT")
    except (dns.exception.DNSException, OSError):
        return []
    return [b"".join(r.strings).decode(errors="replace") for r in answer]


@dataclass
class _Deps:
    """Replaceable in tests (fake resolver, fake transport)."""

    txt: Any = _dns_txt
    transport: httpx.AsyncBaseTransport | None = None
    resolve: Any = resolve_host


DEPS = _Deps()


def normalise_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def target_host(cfg: TargetConfig) -> str | None:
    if cfg.kind == "hosted":
        return None
    url = cfg.base_url if cfg.kind == "openai_compat" else cfg.url
    h = urlsplit(url).hostname
    return normalise_host(h) if h else None


def is_remote(cfg: TargetConfig, settings: Settings) -> bool:
    """Hosted targets, loopback and `GAUNTLET_LOCAL_TARGET_HOSTS` are local; all else remote."""
    host = target_host(cfg)
    if host is None:
        return False
    if host in {h.lower() for h in settings.local_target_hosts}:
        return False
    try:
        if ipaddress.ip_address(host).is_loopback:
            return False
    except ValueError:
        pass
    return host != "localhost"


def _check_verifiable(host: str) -> None:
    try:
        ipaddress.ip_address(host.strip("[]"))
        literal = True
    except ValueError:
        literal = False
    if literal or not _EXTRACT(host).domain:  # an IP literal, a bare public suffix or nonsense
        raise ApiError(422, "unverifiable_host", f"{host!r} cannot be verified")


def instructions(v: TargetVerification) -> dict[str, str]:
    if v.method == "dns":
        return {
            "record_type": "TXT",
            "record_name": f"{CHALLENGE_LABEL}.{v.host}",
            "record_value": f"gauntlet-verify={v.token}",
        }
    return {"url": f"https://{v.host}{WELL_KNOWN}", "body": v.token}


async def request_verification(
    session: AsyncSession, workspace_id: str, host: str, method: str
) -> TargetVerification:
    host = normalise_host(host)
    _check_verifiable(host)
    row = (
        await session.execute(
            select(TargetVerification).where(
                TargetVerification.workspace_id == workspace_id, TargetVerification.host == host
            )
        )
    ).scalar_one_or_none()
    token = "gv_" + secrets.token_urlsafe(18)
    if row is None:
        row = TargetVerification(
            id=new_id("tvf"), workspace_id=workspace_id, host=host, method=method, token=token
        )
        session.add(row)
    else:  # re-requesting restarts the challenge
        row.method, row.token, row.status = method, token, "pending"
        row.verified_at = row.expires_at = row.detail = None
    await session.flush()
    return row


async def _http_check(v: TargetVerification) -> tuple[bool, str]:
    inner = DEPS.transport or httpx.AsyncHTTPTransport()
    policy = UrlPolicy(allow_private=False, local_hosts=frozenset())
    async with httpx.AsyncClient(
        transport=GuardedTransport(inner, policy, DEPS.resolve), follow_redirects=False, timeout=10
    ) as c:
        r = await c.get(f"https://{v.host}{WELL_KNOWN}")
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    return r.text.strip() == v.token, "token mismatch"


async def check_verification(
    session: AsyncSession, v: TargetVerification, settings: Settings
) -> TargetVerification:
    ok, detail = False, "token not found"
    try:
        if v.method == "dns":
            values = await DEPS.txt(f"{CHALLENGE_LABEL}.{v.host}")
            ok = f"gauntlet-verify={v.token}" in [x.strip() for x in values]
        else:
            ok, detail = await _http_check(v)
    except (TargetError, httpx.HTTPError, OSError) as e:
        detail = f"check failed: {e}"
    now = datetime.now(UTC)
    v.last_checked_at = now
    if ok:
        v.status, v.verified_at, v.detail = "verified", now, None
        v.expires_at = now + timedelta(days=settings.verification_ttl_days)
    else:
        v.status, v.detail = "failed", detail
    await session.flush()
    return v


async def covering_verification(
    session: AsyncSession, workspace_id: str, host: str
) -> TargetVerification | None:
    """A verified, unexpired record for `host` or a parent domain of it."""
    host = normalise_host(host)
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(TargetVerification).where(
                TargetVerification.workspace_id == workspace_id,
                TargetVerification.status == "verified",
            )
        )
    ).scalars()
    for v in rows:
        if v.expires_at is not None and v.expires_at < now:
            continue
        if host == v.host or host.endswith("." + v.host):
            return v
    return None


async def require_target_verified(
    session: AsyncSession, settings: Settings, workspace_id: str, cfg: TargetConfig
) -> None:
    if not is_remote(cfg, settings):
        return
    host = target_host(cfg)
    assert host is not None
    if await covering_verification(session, workspace_id, host) is None:
        raise ApiError(
            403, "target_not_verified", f"target host {host!r} is not verified", {"host": host}
        )
