"""Alert channels, rules, de-duplicated alerts and signed delivery (P5-7).

Opt-in and offline by default (CQ-P10): a channel stores only the *name* of a secret; the URL
or SMTP credentials live in the secret store and appear in no row, log line or response. With
no channel configured nothing is sent. Delivery runs as a job (`alert_deliver`):

- webhook: secret value is JSON `{"url": ..., "signing_key": ...}`. The body is canonical JSON,
  signed `HMAC-SHA256(key, f"{timestamp}.{body}")` in `X-Gauntlet-Signature: sha256=<hex>`
  with `X-Gauntlet-Timestamp`.
- slack: secret value is the incoming-webhook URL.
- email: secret value is JSON `{"host","port","username","password","from","to":[...],
  "starttls": true}`; sent with `smtplib` in a thread.

Webhook and Slack URLs pass the same SSRF guard as targets (`GuardedTransport`). Delivery
retries with backoff inside the job; a failure after the retries fails the job, which the queue
retries again."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import smtplib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any, Literal

import httpx
from gauntlet_core.ids import new_id
from gauntlet_core.slo import SloStatus
from gauntlet_core.targets.safety import GuardedTransport, UrlPolicy, resolve_host
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as m
from ..db.ops_models import Alert, AlertChannel, AlertRule, Slo
from ..db.policy_models import GatewayDecisionRow
from ..db.sec_models import Finding
from ..deps import AppState
from ..errors import ApiError, not_found
from ..stores.jobs import PgJobQueue
from .audit import audit
from .gateway import parse_window
from .jobs import JobContext, handler
from .slo import SloStatusOut, slo_samples, slo_status_out, status_of

__all__ = [
    "AlertOut",
    "ChannelIn",
    "ChannelOut",
    "ChannelPatch",
    "RuleIn",
    "RuleOut",
    "RulePatch",
    "SilenceIn",
    "create_channel",
    "create_rule",
    "evaluate_all",
    "list_alerts",
    "list_channels",
    "list_rules",
    "sign",
    "silence_alert",
    "update_channel",
    "update_rule",
]

log = logging.getLogger("gauntlet.alerts")

BACKOFF_S: tuple[float, ...] = (1.0, 4.0)  # waits between the three attempts
SEVERITY_ORDER = ("low", "medium", "high", "critical")
MAX_FINDING_ALERTS = 20
resolve: Callable[[str], Awaitable[list[str]]] = resolve_host  # tests replace this
SMTP_FACTORY: Callable[..., smtplib.SMTP] = smtplib.SMTP  # tests replace this
sleep: Callable[[float], Awaitable[None]] = asyncio.sleep  # tests replace this

Kind = Literal["burn", "breach", "finding", "gateway_block_rate"]


# --------------------------------------------------------------------------- models


class ChannelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["webhook", "slack", "email"]
    secret_name: str = Field(min_length=1, description="name of the stored secret, never its value")


class ChannelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secret_name: str = Field(min_length=1)


class ChannelOut(BaseModel):
    id: str
    kind: str
    secret_name: str
    created_at: datetime


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    slo_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    channel_ids: list[str] = Field(default_factory=list)


class RulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    params: dict[str, Any] | None = None
    channel_ids: list[str] | None = None
    silence_until: datetime | None = None


class RuleOut(BaseModel):
    id: str
    kind: str
    slo_id: str | None
    params: dict[str, Any]
    channel_ids: list[str]
    silence_until: datetime | None
    created_at: datetime


class AlertOut(BaseModel):
    id: str
    rule_id: str
    fingerprint: str
    state: str
    payload: dict[str, Any]
    first_at: datetime
    last_at: datetime
    notified_at: datetime | None
    silenced_until: datetime | None = None


class SilenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    until: datetime


# --------------------------------------------------------------------------- channels and rules


def _chan(r: AlertChannel) -> ChannelOut:
    return ChannelOut.model_validate(r, from_attributes=True)


def _rule(r: AlertRule) -> RuleOut:
    return RuleOut.model_validate(r, from_attributes=True)


def _parse_secret(kind: str, value: str) -> dict[str, Any]:
    if kind == "slack":
        return {"url": value.strip()}
    try:
        doc = json.loads(value)
        if not isinstance(doc, dict):
            raise ValueError
    except ValueError as e:
        raise ApiError(422, "bad_secret", f"the {kind} secret must be a JSON object") from e
    need = ("url", "signing_key") if kind == "webhook" else ("host", "from", "to")
    if any(k not in doc for k in need):
        raise ApiError(422, "bad_secret", f"the {kind} secret needs {', '.join(need)}")
    return doc


async def _check_secret(state: AppState, ws: str, kind: str, name: str) -> None:
    found = await state.secrets.resolve(ws, [name])
    if name not in found:
        raise ApiError(422, "unknown_secret", f"no secret named {name!r}")
    _parse_secret(kind, found[name])  # shape only; the value never leaves this function


async def create_channel(
    state: AppState, s: AsyncSession, ws: str, body: ChannelIn, actor: str
) -> ChannelOut:
    await _check_secret(state, ws, body.kind, body.secret_name)
    row = AlertChannel(
        id=new_id("chn"), workspace_id=ws, kind=body.kind, secret_name=body.secret_name
    )
    s.add(row)
    await audit(s, ws, actor, "alert_channel.create", "alert_channel", row.id, {"kind": body.kind})
    await s.commit()
    await s.refresh(row)
    return _chan(row)


async def list_channels(s: AsyncSession, ws: str) -> list[ChannelOut]:
    rows = (
        await s.execute(
            select(AlertChannel)
            .where(AlertChannel.workspace_id == ws)
            .order_by(AlertChannel.created_at)
        )
    ).scalars()
    return [_chan(r) for r in rows]


async def update_channel(
    state: AppState, s: AsyncSession, ws: str, cid: str, body: ChannelPatch, actor: str
) -> ChannelOut:
    row = await s.get(AlertChannel, cid)
    if row is None or row.workspace_id != ws:
        raise not_found("alert channel", cid)
    await _check_secret(state, ws, row.kind, body.secret_name)
    row.secret_name = body.secret_name
    await audit(s, ws, actor, "alert_channel.update", "alert_channel", cid, {})
    await s.commit()
    await s.refresh(row)
    return _chan(row)


def _validate_params(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    if kind == "finding":
        sev = params.get("min_severity", "high")
        if sev not in SEVERITY_ORDER:
            raise ApiError(422, "bad_params", f"min_severity is one of {SEVERITY_ORDER}")
        return {"min_severity": sev}
    if kind == "gateway_block_rate":
        window = str(params.get("window", "1h"))
        parse_window(window)
        thr = float(params.get("threshold", 0.5))
        if not 0 < thr <= 1:
            raise ApiError(422, "bad_params", "threshold is in (0, 1]")
        return {
            "window": window,
            "threshold": thr,
            "min_decisions": int(params.get("min_decisions", 20)),
        }
    return {}


async def _check_rule_refs(
    s: AsyncSession, ws: str, kind: str, slo_id: str | None, channel_ids: list[str]
) -> None:
    if kind in ("burn", "breach") and slo_id is None:
        raise ApiError(422, "bad_rule", f"a {kind} rule needs an slo_id")
    if slo_id is not None:
        slo = await s.get(Slo, slo_id)
        if slo is None or slo.workspace_id != ws:
            raise not_found("slo", slo_id)
    for cid in channel_ids:
        ch = await s.get(AlertChannel, cid)
        if ch is None or ch.workspace_id != ws:
            raise not_found("alert channel", cid)


async def create_rule(s: AsyncSession, ws: str, body: RuleIn, actor: str) -> RuleOut:
    await _check_rule_refs(s, ws, body.kind, body.slo_id, body.channel_ids)
    row = AlertRule(
        id=new_id("alr"), workspace_id=ws, slo_id=body.slo_id, kind=body.kind,
        params=_validate_params(body.kind, body.params), channel_ids=list(body.channel_ids),
    )  # fmt: skip
    s.add(row)
    await audit(s, ws, actor, "alert_rule.create", "alert_rule", row.id, {"kind": body.kind})
    await s.commit()
    await s.refresh(row)
    return _rule(row)


async def list_rules(s: AsyncSession, ws: str) -> list[RuleOut]:
    rows = (
        await s.execute(
            select(AlertRule).where(AlertRule.workspace_id == ws).order_by(AlertRule.created_at)
        )
    ).scalars()
    return [_rule(r) for r in rows]


async def update_rule(s: AsyncSession, ws: str, rid: str, body: RulePatch, actor: str) -> RuleOut:
    row = await s.get(AlertRule, rid)
    if row is None or row.workspace_id != ws:
        raise not_found("alert rule", rid)
    if body.params is not None:
        row.params = _validate_params(row.kind, body.params)
    if body.channel_ids is not None:
        await _check_rule_refs(s, ws, row.kind, row.slo_id, body.channel_ids)
        row.channel_ids = list(body.channel_ids)
    if "silence_until" in body.model_fields_set:
        row.silence_until = body.silence_until
    await audit(s, ws, actor, "alert_rule.update", "alert_rule", rid,
                {"fields": sorted(body.model_fields_set)})  # fmt: skip
    await s.commit()
    await s.refresh(row)
    return _rule(row)


async def list_alerts(s: AsyncSession, ws: str, state: str | None) -> list[AlertOut]:
    q = (
        select(Alert, AlertRule.silence_until)
        .join(AlertRule, AlertRule.id == Alert.rule_id)
        .where(Alert.workspace_id == ws)
        .order_by(Alert.last_at.desc())
        .limit(200)
    )
    if state is not None:
        if state not in ("firing", "resolved"):
            raise ApiError(422, "validation_error", "state is firing or resolved")
        q = q.where(Alert.state == state)
    out = []
    for a, silence in (await s.execute(q)).all():
        o = AlertOut.model_validate(a, from_attributes=True)
        o.silenced_until = silence
        out.append(o)
    return out


async def silence_alert(
    s: AsyncSession, ws: str, alert_id: str, until: datetime, actor: str
) -> AlertOut:
    """Silences the alert's rule until `until` (alerts of one rule share the silence)."""
    a = await s.get(Alert, alert_id)
    if a is None or a.workspace_id != ws:
        raise not_found("alert", alert_id)
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    rule = await s.get(AlertRule, a.rule_id)
    assert rule is not None
    rule.silence_until = until
    await audit(s, ws, actor, "alert.silence", "alert", alert_id,
                {"rule_id": rule.id, "until": until.isoformat()})  # fmt: skip
    await s.commit()
    out = AlertOut.model_validate(a, from_attributes=True)
    out.silenced_until = until
    return out


# --------------------------------------------------------------------------- evaluation


async def _slo_states(
    s: AsyncSession, cache: dict[str, tuple[Slo, SloStatus] | None], slo_id: str, now: datetime
) -> tuple[Slo, SloStatus] | None:
    if slo_id not in cache:
        slo = await s.get(Slo, slo_id)
        cache[slo_id] = (
            (slo, status_of(slo, await slo_samples(s, slo, now), now))
            if slo is not None and slo.enabled
            else None
        )
    return cache[slo_id]


async def _conditions(
    s: AsyncSession, rule: AlertRule, now: datetime, cache: dict[str, tuple[Slo, SloStatus] | None]
) -> dict[str, dict[str, Any]]:
    """Fingerprint -> payload for every condition that holds now. Payloads carry ids and
    numbers only."""
    out: dict[str, dict[str, Any]] = {}
    if rule.kind in ("burn", "breach") and rule.slo_id:
        got = await _slo_states(s, cache, rule.slo_id, now)
        if got is None:
            return out
        slo, st = got
        view: SloStatusOut = slo_status_out(slo, st)
        base = {"slo_id": slo.id, "metric": slo.metric, "state": st.state, "n": st.n}
        if rule.kind == "breach" and st.breached:
            out[f"breach:{slo.id}"] = {**base, "value": view.value, "objective": slo.objective}
        if rule.kind == "burn":
            for name in view.firing_burn_alerts:
                if name in slo.burn_alerts:
                    out[f"burn:{slo.id}:{name}"] = {**base, "pair": name, "burn": st.burn_rates}
    elif rule.kind == "finding":
        floor = SEVERITY_ORDER.index(rule.params.get("min_severity", "high"))
        wanted = SEVERITY_ORDER[floor:]
        q = (
            select(Finding.id, Finding.severity, Finding.category)
            .where(
                Finding.workspace_id == rule.workspace_id,
                Finding.status == "open",
                Finding.severity.in_(wanted),
            )
            .order_by(Finding.created_at.desc())
            .limit(MAX_FINDING_ALERTS)
        )
        if rule.slo_id:
            slo = await s.get(Slo, rule.slo_id)
            if slo is not None:
                q = q.join(m.AgentVersion, m.AgentVersion.id == Finding.agent_version_id).where(
                    m.AgentVersion.agent_id == slo.agent_id
                )
        for fid, sev, cat in (await s.execute(q)).all():
            out[f"finding:{fid}"] = {"finding_id": fid, "severity": sev, "category": cat}
    elif rule.kind == "gateway_block_rate":
        since = now - timedelta(seconds=parse_window(rule.params.get("window", "1h")))
        total, blocked = (
            await s.execute(
                select(
                    func.count(),
                    func.count().filter(GatewayDecisionRow.action == "block"),
                ).where(
                    GatewayDecisionRow.workspace_id == rule.workspace_id,
                    GatewayDecisionRow.ts >= since,
                )
            )
        ).one()
        if total >= int(rule.params.get("min_decisions", 20)) and (
            blocked / total >= float(rule.params.get("threshold", 0.5))
        ):
            out["gateway_block_rate"] = {"decisions": total, "blocked": blocked,
                                         "rate": blocked / total}  # fmt: skip
    return out


async def _job_pending(s: AsyncSession, alert_id: str) -> bool:
    row = await s.execute(
        text(
            "SELECT 1 FROM jobs WHERE kind = 'alert_deliver' AND status IN ('queued','running') "
            "AND payload ->> 'alert_id' = :a LIMIT 1"
        ),
        {"a": alert_id},
    )
    return row.first() is not None


async def evaluate_rule(
    state: AppState,
    s: AsyncSession,
    rule: AlertRule,
    now: datetime,
    cache: dict[str, tuple[Slo, SloStatus] | None],
) -> None:
    active = await _conditions(s, rule, now, cache)
    existing = {
        a.fingerprint: a
        for a in (await s.execute(select(Alert).where(Alert.rule_id == rule.id))).scalars()
    }
    for fp, payload in active.items():
        a = existing.get(fp)
        if a is None:
            a = Alert(
                id=new_id("alt"), workspace_id=rule.workspace_id, rule_id=rule.id,
                fingerprint=fp, state="firing", payload=payload, first_at=now, last_at=now,
            )  # fmt: skip
            s.add(a)
            existing[fp] = a
        elif a.state == "resolved":
            a.state, a.first_at, a.last_at, a.payload = "firing", now, now, payload
        else:
            a.last_at, a.payload = now, payload
    for fp, a in existing.items():
        if fp not in active and a.state == "firing":
            a.state, a.last_at = "resolved", now
    await s.flush()
    silenced = rule.silence_until is not None and rule.silence_until > now
    if not rule.channel_ids or silenced:
        return
    queue = PgJobQueue(state.sm)
    for a in existing.values():
        if a.state == a.notified_state:
            continue
        if a.state == "resolved" and a.notified_state != "firing":
            continue  # never announced, nothing to resolve
        if await _job_pending(s, a.id):
            continue
        await queue.enqueue(
            rule.workspace_id, "alert_deliver", {"alert_id": a.id, "event": a.state}, session=s
        )


async def evaluate_all(state: AppState, now: datetime | None = None) -> int:
    """Worker tick: evaluate every rule, enqueue notifications for new or resolved alerts."""
    now = now or datetime.now(UTC)
    async with state.sm() as s:
        rule_ids = list((await s.execute(select(AlertRule.id))).scalars())
    cache: dict[str, tuple[Slo, SloStatus] | None] = {}
    for rid in rule_ids:
        try:
            async with state.sm() as s, s.begin():
                rule = await s.get(AlertRule, rid)
                if rule is not None:
                    await evaluate_rule(state, s, rule, now, cache)
        except Exception:
            log.exception("alert rule %s failed to evaluate", rid)
    return len(rule_ids)


# --------------------------------------------------------------------------- delivery


class DeliveryError(Exception):
    """Carries a channel id and a reason that never includes a URL or credential."""


def sign(key: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(key.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def _body(alert: Alert, rule: AlertRule, event: str) -> bytes:
    doc = {
        "id": alert.id, "event": event, "kind": rule.kind, "rule_id": rule.id,
        "fingerprint": alert.fingerprint, "state": alert.state, "payload": alert.payload,
        "first_at": alert.first_at.isoformat(), "last_at": alert.last_at.isoformat(),
    }  # fmt: skip
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def _summary(alert: Alert, rule: AlertRule, event: str) -> str:
    verb = "RESOLVED" if event == "resolved" else "FIRING"
    return f"[Gauntlet] {verb}: {rule.kind} ({alert.fingerprint})"


def _client(state: AppState) -> httpx.AsyncClient:
    policy = UrlPolicy(
        allow_private=state.settings.allow_private_targets,
        local_hosts=state.settings.local_target_hosts if state.settings.is_dev else frozenset(),
    )
    return httpx.AsyncClient(
        transport=GuardedTransport(httpx.AsyncHTTPTransport(), policy, lambda h: resolve(h)),
        timeout=10.0,
        follow_redirects=False,
    )


async def _post(
    state: AppState, channel: AlertChannel, url: str, body: bytes, headers: dict[str, str]
) -> None:
    last = "unknown"
    for attempt in range(len(BACKOFF_S) + 1):
        try:
            async with _client(state) as c:
                r = await c.post(url, content=body, headers=headers)
            if r.status_code < 300:
                return
            last = f"http {r.status_code}"
            if r.status_code < 500 and r.status_code != 429:
                break  # a client error will not improve by retrying
        except Exception as e:  # message may carry the URL: keep the class name only
            last = type(e).__name__
        if attempt < len(BACKOFF_S):
            await sleep(BACKOFF_S[attempt])
    raise DeliveryError(f"{channel.id}: {channel.kind} delivery failed ({last})")


async def _send_email(channel: AlertChannel, cfg: dict[str, Any], subject: str, body: str) -> None:
    def go() -> None:
        msg = EmailMessage()
        msg["Subject"], msg["From"] = subject, cfg["from"]
        to = cfg["to"] if isinstance(cfg["to"], list) else [cfg["to"]]
        msg["To"] = ", ".join(to)
        msg.set_content(body)
        with SMTP_FACTORY(cfg["host"], int(cfg.get("port", 587)), timeout=15) as smtp:
            if cfg.get("starttls", True):
                smtp.starttls()
            if cfg.get("username"):
                smtp.login(cfg["username"], cfg.get("password", ""))
            smtp.send_message(msg)

    last = "unknown"
    for attempt in range(len(BACKOFF_S) + 1):
        try:
            await asyncio.to_thread(go)
            return
        except Exception as e:
            last = type(e).__name__
            if attempt < len(BACKOFF_S):
                await sleep(BACKOFF_S[attempt])
    raise DeliveryError(f"{channel.id}: email delivery failed ({last})")


async def deliver(
    state: AppState, alert: Alert, rule: AlertRule, channel: AlertChannel, event: str
) -> None:
    secrets = await state.secrets.resolve(channel.workspace_id, [channel.secret_name])
    if channel.secret_name not in secrets:
        raise DeliveryError(f"{channel.id}: the channel's secret is missing")
    cfg = _parse_secret(channel.kind, secrets[channel.secret_name])
    body = _body(alert, rule, event)
    if channel.kind == "webhook":
        ts = str(int(datetime.now(UTC).timestamp()))
        headers = {
            "content-type": "application/json", "x-gauntlet-event": event,
            "x-gauntlet-timestamp": ts, "x-gauntlet-signature": sign(cfg["signing_key"], ts, body),
        }  # fmt: skip
        await _post(state, channel, cfg["url"], body, headers)
    elif channel.kind == "slack":
        text_body = json.dumps({"text": _summary(alert, rule, event)}).encode()
        await _post(state, channel, cfg["url"], text_body, {"content-type": "application/json"})
    else:
        await _send_email(channel, cfg, _summary(alert, rule, event), body.decode())


@handler("alert_deliver")
async def alert_deliver(ctx: JobContext) -> dict[str, Any]:
    event = str(ctx.payload["event"])
    async with ctx.state.sm() as s:
        alert = await s.get(Alert, ctx.payload["alert_id"])
        if alert is None or alert.state != event:
            return {"skipped": "stale"}  # the state moved on; a newer job covers it
        rule = await s.get(AlertRule, alert.rule_id)
        assert rule is not None
        channels = [
            c
            for cid in rule.channel_ids
            if (c := await s.get(AlertChannel, cid)) is not None
            and c.workspace_id == alert.workspace_id
        ]
    delivered = 0
    errors: list[str] = []
    for ch in channels:
        try:
            await deliver(ctx.state, alert, rule, ch, event)
            delivered += 1
        except DeliveryError as e:
            errors.append(str(e))
    if errors:
        raise DeliveryError("; ".join(errors))
    async with ctx.state.sm() as s, s.begin():
        row = await s.get(Alert, alert.id)
        assert row is not None
        row.notified_at, row.notified_state = datetime.now(UTC), event
    return {"delivered": delivered}
