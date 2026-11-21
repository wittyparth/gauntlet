"""Worker process: claims episodes, runs them through the shared runner, heartbeats leases.

`python -m gauntlet_server.worker`. Per episode: one task running `execute_with_attempts`
(the abandon-attempt path for `IndeterminateEffect`, hard-cores 1.7a) and one heartbeat task
every `lease_s / 3`. A lost lease (heartbeat False, `StaleLease`) cancels the episode task and
writes nothing more. SIGTERM stops claiming and releases live leases.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
import signal
import socket
from typing import Any

import httpx
from gauntlet_core.engine import (
    EpisodeCtx,
    EpisodeLease,
    NonDeterminism,
    StaleLease,
)
from gauntlet_core.ids import new_id
from gauntlet_core.runner import MAX_ATTEMPTS, EpisodeOutcome, RunnerDeps, execute_with_attempts
from gauntlet_core.schema import EventDraft
from gauntlet_core.targets import UrlPolicy
from sqlalchemy import text

from .deps import AppState
from .events import PublishingJournalStore
from .facade import RemoteFacade
from .jobs import load_episode_job
from .limits import HostLimiter, LimitedTransport
from .models_gateway import gateway_for_roles
from .services.adaptive import adaptive_after_episode
from .services.finding_hooks import after_episode
from .services.killswitch import KILL_PREFIX, cancel_attack_runs, engaged_keys, killswitch_engaged
from .services.ownership import covering_verification, is_remote, target_host
from .services.runs import maybe_complete_run, run_update_payload
from .stores import PgBudgetLedger, PgEpisodeQueue, PgJournalStore

__all__ = ["Worker", "main"]

log = logging.getLogger("gauntlet.worker")


class Worker:
    def __init__(
        self,
        state: AppState,
        *,
        worker_id: str | None = None,
        concurrency: int | None = None,
        lease_s: int | None = None,
        poll_interval_s: float | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        s = state.settings
        self.state = state
        self.id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{new_id('w')[-6:]}"
        self.concurrency = concurrency or s.worker_concurrency
        self.lease_s = lease_s or s.lease_s
        self.poll_s = poll_interval_s if poll_interval_s is not None else s.poll_interval_s
        self._own_http: httpx.AsyncClient | None = None
        if http is None and state.redis is not None:
            limiter = HostLimiter(state.redis)
            transport = LimitedTransport(httpx.AsyncHTTPTransport(), limiter, s.local_target_hosts)
            http = self._own_http = httpx.AsyncClient(transport=transport)
        self.http = http or state.http
        # attack episodes in flight: episode id -> (run id, workspace id), for the kill switch
        self._attack_eps: dict[str, tuple[str, str]] = {}
        self.queue = PgEpisodeQueue(state.sm)
        self._tasks: dict[str, tuple[asyncio.Task[None], EpisodeLease]] = {}
        self._killed = False
        self._stopping = False
        self.active_run: str | None = None  # tests: only claim for logging

    # ------------------------------------------------------------------ loop

    async def run(self, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        log.info("worker %s started (concurrency %d)", self.id, self.concurrency)
        watcher = asyncio.create_task(self._kill_watch(stop))
        try:
            await self._loop(stop)
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            if self._own_http is not None:
                await self._own_http.aclose()

    async def _loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set() and not self._killed:
            free = self.concurrency - len(self._tasks)
            if free > 0:
                try:
                    for lease in await self.queue.claim(self.id, free, self.lease_s):
                        self._start(lease)
                except Exception:
                    log.exception("claim failed")
            delay = self.poll_s * (1 + random.random() * 0.25)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
        if not self._killed:
            await self.shutdown()

    # ------------------------------------------------------------------ kill switch

    async def _kill_watch(self, stop: asyncio.Event) -> None:
        """Poll Redis only (never Postgres) and cancel attack episodes while a switch is
        engaged: in-flight tasks (cancelling their httpx requests), then queued episodes."""
        redis = self.state.redis
        if redis is None:
            return
        while not stop.is_set() and not self._killed:
            await asyncio.sleep(self.state.settings.kill_poll_s)
            try:
                keys = await engaged_keys(redis)
                if not keys:
                    continue
                for eid, (task, lease) in list(self._tasks.items()):
                    info = self._attack_eps.get(eid)
                    if info and await killswitch_engaged(redis, info[1], info[0]):
                        await self._mark_cancelled(lease)
                        task.cancel()
                await self._cancel_engaged(keys)
            except Exception:
                log.warning("kill watcher error", exc_info=True)

    async def _cancel_engaged(self, keys: list[str]) -> None:
        async with self.state.sm() as s, s.begin():
            for k in keys:
                name = k[len(KILL_PREFIX) :]
                if name.startswith("run:"):
                    rid = name[4:]
                    ws = (
                        await s.execute(
                            text("SELECT workspace_id FROM runs WHERE id = :r"), {"r": rid}
                        )
                    ).scalar()
                    if ws:
                        await cancel_attack_runs(s, ws, rid)
                else:
                    await cancel_attack_runs(s, name, None)

    async def _attack_guard(self, lease: EpisodeLease, job: Any) -> bool:
        """Re-check kill switch and ownership before an attack episode starts. True = stop."""
        async with self.state.sm() as s:
            ws = str(
                (
                    await s.execute(
                        text("SELECT workspace_id FROM runs WHERE id = :r"), {"r": lease.run_id}
                    )
                ).scalar()
            )
        self._attack_eps[lease.episode_id] = (lease.run_id, ws)
        redis = self.state.redis
        if redis is not None and await killswitch_engaged(redis, ws, lease.run_id):
            await self._mark_cancelled(lease)
            return True
        cfg = job.agent_version.target
        host = target_host(cfg)
        if host and is_remote(cfg, self.state.settings):
            async with self.state.sm() as s:
                ok = await covering_verification(s, ws, host) is not None
            if not ok:
                async with self.state.sm() as s, s.begin():
                    await cancel_attack_runs(s, ws, lease.run_id)
                await self._fail(lease, "target_not_verified")
                return True
        return False

    async def shutdown(self) -> None:
        """Graceful: stop claiming, cancel tasks, hand every live lease back."""
        self._stopping = True
        live = list(self._tasks.values())
        for task, _ in live:
            task.cancel()
        await asyncio.gather(*(t for t, _ in live), return_exceptions=True)
        for _, lease in live:
            with contextlib.suppress(Exception):
                await self.queue.release(lease, retry_after_s=0)
        self._tasks.clear()
        log.info("worker %s stopped", self.id)

    async def kill(self) -> None:
        """Simulate a SIGKILL (tests): stop everything, write and release nothing."""
        self._killed = True
        tasks = [t for t, _ in self._tasks.values()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _start(self, lease: EpisodeLease) -> None:
        task = asyncio.create_task(self._run_one(lease), name=f"episode:{lease.episode_id}")
        self._tasks[lease.episode_id] = (task, lease)
        task.add_done_callback(lambda _t, eid=lease.episode_id: self._tasks.pop(eid, None))

    async def run_leases(self, leases: list[EpisodeLease]) -> None:
        """Run already-claimed leases to completion (the dev seed and tests use this)."""
        for lease in leases:
            self._start(lease)
        await asyncio.gather(*(t for t, _ in list(self._tasks.values())), return_exceptions=True)

    # --------------------------------------------------------------- one episode

    async def _run_one(self, lease: EpisodeLease) -> None:
        me = asyncio.current_task()
        assert me is not None
        beat = asyncio.create_task(self._heartbeat(lease, me))
        try:
            await self._execute(lease)
        except asyncio.CancelledError:
            raise
        except StaleLease:
            log.info("lease on %s lost; dropping", lease.episode_id)
        except Exception:
            log.exception("episode %s crashed in the worker", lease.episode_id)
            await self._retry_or_fail(lease)
        finally:
            beat.cancel()
            self._attack_eps.pop(lease.episode_id, None)

    async def _heartbeat(self, lease: EpisodeLease, task: asyncio.Task[Any]) -> None:
        while True:
            await asyncio.sleep(self.lease_s / 3)
            try:
                alive = await self.queue.heartbeat(lease)
                status = await self._run_status(lease.run_id)
            except Exception:
                log.warning("heartbeat error for %s", lease.episode_id, exc_info=True)
                continue
            if not alive:
                log.info("heartbeat lost for %s; cancelling", lease.episode_id)
                task.cancel()
                return
            if status == "cancelled":
                await self._mark_cancelled(lease)
                task.cancel()
                return

    async def _run_status(self, run_id: str) -> str | None:
        async with self.state.sm() as s:
            return (
                await s.execute(text("SELECT status FROM runs WHERE id = :r"), {"r": run_id})
            ).scalar()

    async def _mark_cancelled(self, lease: EpisodeLease) -> None:
        async with self.state.sm() as s, s.begin():
            await s.execute(
                text(
                    "UPDATE episodes SET status = 'cancelled', finished_at = now(), "
                    "lease_owner = NULL WHERE id = :id AND epoch = :e AND status = 'leased'"
                ),
                {"id": lease.episode_id, "e": lease.epoch},
            )

    async def _run_roles(self, run_id: str) -> dict[str, Any] | None:
        async with self.state.sm() as s:
            row = (
                await s.execute(text("SELECT role_settings FROM runs WHERE id = :r"), {"r": run_id})
            ).scalar()
        return row if isinstance(row, dict) else None

    def _deps(self, run_id: str, roles: dict[str, Any] | None = None) -> RunnerDeps:
        st = self.state
        return RunnerDeps(
            store=PublishingJournalStore(PgJournalStore(st.sm), st.publisher, run_id),
            gateway=gateway_for_roles(st.gateway, roles),
            budget=PgBudgetLedger(st.sm),
            http=self.http,
            url_policy=UrlPolicy(
                allow_private=st.settings.allow_private_targets,
                local_hosts=st.settings.local_target_hosts,
            ),
            facade=RemoteFacade(st.settings.public_api_url, st.settings.mock_secret()),
        )

    async def _execute(self, lease: EpisodeLease) -> None:
        await self._publish_episode(lease)
        await self._publish_run(lease.run_id)
        try:
            async with self.state.sm() as s:
                job = await load_episode_job(s, lease.episode_id, self.state.secrets)
        except (LookupError, ValueError) as e:
            await self._fail(lease, f"cannot load episode: {e}")
            return
        if job.scenario.attack is not None and await self._attack_guard(lease, job):
            await self._publish_episode(lease)
            await self._publish_run(lease.run_id)
            return
        deps = self._deps(lease.run_id, await self._run_roles(lease.run_id))
        try:
            out = await execute_with_attempts(job, deps, epoch=lease.epoch)
        except NonDeterminism as e:
            await self._fail(lease, f"NonDeterminism: {e}")
            return
        await self._finish(lease, out)

    async def _finish(self, lease: EpisodeLease, out: EpisodeOutcome) -> None:
        try:  # findings hook: before the episode is `done`, so a run never completes without it
            await after_episode(self.state.sm, lease.episode_id, out.outcome)
        except Exception:
            log.exception("finding hook failed for %s", lease.episode_id)
        await self.queue.finish(lease, out.outcome, out.termination)  # StaleLease: dropped
        async with self.state.sm() as s, s.begin():
            await s.execute(
                text(
                    "UPDATE episodes SET world_fidelity = :w, latency_ms = :lat, "
                    "tokens_in = :tin, tokens_out = :tout WHERE id = :id"
                ),
                {
                    "w": out.world_fidelity,
                    "lat": out.latency_ms,
                    "tin": out.cost.input_tokens,
                    "tout": out.cost.output_tokens,
                    "id": lease.episode_id,
                },
            )
            for v in out.verdicts:
                await s.execute(
                    text(
                        "INSERT INTO verdicts (id, workspace_id, episode_id, evaluator, "
                        "criterion, result, doc) SELECT :id, workspace_id, :ep, :ev, :cr, :res, "
                        "CAST(:doc AS jsonb) FROM episodes WHERE id = :ep"
                    ),
                    {
                        "id": new_id("vrd"),
                        "ep": lease.episode_id,
                        "ev": v.evaluator,
                        "cr": v.criterion,
                        "res": v.result,
                        "doc": v.model_dump_json(),
                    },
                )
            if out.outcome == "budget_exhausted":
                await s.execute(
                    text(
                        "UPDATE episodes SET status = 'cancelled', finished_at = now() "
                        "WHERE run_id = :r AND status = 'queued'"
                    ),
                    {"r": lease.run_id},
                )
            await adaptive_after_episode(s, lease.episode_id)  # may add one more repetition
            await maybe_complete_run(s, lease.run_id)
        await self._publish_episode(lease)
        await self._publish_run(lease.run_id)

    async def _fail(self, lease: EpisodeLease, detail: str) -> None:
        """End the episode as platform_error, with an `episode_ended` event for the record."""
        log.error("episode %s: %s", lease.episode_id, detail)
        store = PublishingJournalStore(
            PgJournalStore(self.state.sm), self.state.publisher, lease.run_id
        )
        ctx = await EpisodeCtx.open(
            store, lease.episode_id, epoch=lease.epoch, run_id=lease.run_id, rng_seed=0
        )
        ctx.seek_end()
        await ctx.emit(
            EventDraft(
                kind="episode_ended",
                actor="platform",
                sim_time=ctx.now(),
                payload={"outcome": "platform_error", "termination": "error", "detail": detail},
            )
        )
        await ctx.flush()
        await self.queue.finish(lease, "platform_error", "error")
        async with self.state.sm() as s, s.begin():
            await adaptive_after_episode(s, lease.episode_id)
            await maybe_complete_run(s, lease.run_id)
        await self._publish_episode(lease)
        await self._publish_run(lease.run_id)

    async def _retry_or_fail(self, lease: EpisodeLease) -> None:
        """Unexpected exception: archive the partial journal (attempt + 1) and retry later."""
        try:
            store = PgJournalStore(self.state.sm)
            attempt = await store.abandon_attempt(lease.episode_id, lease.epoch)
            if attempt >= MAX_ATTEMPTS:
                await self._fail(lease, f"failed in {MAX_ATTEMPTS} attempts")
            else:
                await self.queue.release(lease, retry_after_s=min(60, 5 * 2 ** (attempt - 1)))
        except StaleLease:
            pass
        except Exception:
            log.exception("could not retry %s", lease.episode_id)

    # ----------------------------------------------------------------- publishing

    async def _publish_episode(self, lease: EpisodeLease) -> None:
        async with self.state.sm() as s:
            row = (
                (
                    await s.execute(
                        text(
                            "SELECT id, scenario_id, rep, status, outcome, termination, "
                            "cost_usd_micros FROM episodes WHERE id = :id"
                        ),
                        {"id": lease.episode_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return
        data = {
            "episode_id": row["id"],
            "scenario_id": row["scenario_id"],
            "rep": row["rep"],
            "status": row["status"],
            "outcome": row["outcome"],
            "termination": row["termination"],
            "cost_usd_micros": row["cost_usd_micros"],
        }
        await self.state.publisher.publish(lease.run_id, "episode_update", data)

    async def _publish_run(self, run_id: str) -> None:
        async with self.state.sm() as s:
            data = await run_update_payload(s, run_id)
        await self.state.publisher.publish(run_id, "run_update", data)


async def main() -> None:
    from .app import build_state

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    state = await build_state()
    worker = Worker(state)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await worker.run(stop)
    finally:
        await state.aclose()


if __name__ == "__main__":
    asyncio.run(main())
