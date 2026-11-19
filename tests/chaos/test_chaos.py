"""Engine chaos (hard-cores 1.8): real worker processes against Postgres, SIGKILLed at random.

Two passes over the same 60 episodes of the e-commerce pack (hosted agent on the scripted
gateway, plus a wired agent that calls the api mock facade): a clean pass, then a pass in
which a killer SIGKILLs a random worker about once a second (and restarts it). The chaos pass
must produce exactly what the clean pass did, with nothing duplicated:

* every episode finishes, with the clean pass's outcome (no `platform_error`);
* no duplicate or missing `seq`; no effect key `done` twice (live and archived attempts);
* the final journal of each episode equals the clean one, so world totals match (one refund
  per refund scenario);
* the run's spend equals the sum of the effect costs, and no reservation is left over.

Needs `TEST_DATABASE_URL`, redis on `TEST_REDIS_URL` and `GAUNTLET_CHAOS=1`.
"""

from __future__ import annotations

import asyncio
import os
import random
import signal
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.chaos]

ROOT = Path(__file__).resolve().parents[2]
KEY = "gk_chaos_local_only"
WORKERS = 3
LEASE_S = 3
LLM_LATENCY_S = 0.12
AGENT_DELAY_S = 0.3
HOSTED_REPS = 4  # 10 smoke scenarios x 4 = 40 episodes
WIRED_REPS = 10  # 2 scenarios x 10 = 20 episodes
WIRED_SCENARIOS = ["scn_ecom_01", "scn_ecom_02"]
KILL_EVERY_S = 1.0
DEADLINE_S = 420


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Stack:
    """The api, the wired agent and a fleet of worker processes, all real subprocesses."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.api_port, self.agent_port = free_port(), free_port()
        self.api_url = f"http://127.0.0.1:{self.api_port}"
        from gauntlet_server.services.seed import script

        fake = {"cost_usd_micros": 1500, **script()}  # hosted agent with real tool calls
        fake_api, fake_workers = tmp / "fake_api.yaml", tmp / "fake_workers.yaml"
        fake_api.write_text(yaml.safe_dump(fake))
        fake_workers.write_text(yaml.safe_dump({**fake, "latency_s": LLM_LATENCY_S}))
        self.env = {
            **os.environ,
            "DATABASE_URL": os.environ["TEST_DATABASE_URL"],
            "REDIS_URL": os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/0"),
            "GAUNTLET_ENV": "dev",
            "GAUNTLET_DEV_API_KEY": KEY,
            "GAUNTLET_PUBLIC_API_URL": self.api_url,
            "LEASE_SECONDS": str(LEASE_S),
            "WORKER_CONCURRENCY": "4",
            "POLL_INTERVAL_S": "0.2",
            "GAUNTLET_LOCAL_TARGET_HOSTS": "127.0.0.1,localhost",
            "PYTHONPATH": str(ROOT),
            # a wired turn cut short by a SIGKILL burns an attempt; the killer is relentless
            "GAUNTLET_MAX_ATTEMPTS": "10",
        }
        self.env.pop("GAUNTLET_PACK_DIR", None)
        self.api_env = {**self.env, "GAUNTLET_GATEWAY": f"fake:{fake_api}"}
        self.worker_env = {**self.env, "GAUNTLET_GATEWAY": f"fake:{fake_workers}"}
        self.procs: list[subprocess.Popen[bytes]] = []
        self.workers: list[subprocess.Popen[bytes]] = []
        self.kills = 0
        self._n = 0

    def _spawn(self, args: list[str], env: dict[str, str], name: str) -> subprocess.Popen[bytes]:
        self._n += 1
        log = (self.tmp / f"{name}-{self._n}.log").open("wb")
        p = subprocess.Popen(
            [sys.executable, *args], env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT
        )
        self.procs.append(p)
        return p

    def start_core(self) -> None:
        self._spawn(
            ["-m", "uvicorn", "gauntlet_server.app:app", "--port", str(self.api_port)],
            self.api_env,
            "api",
        )
        self._spawn(
            ["tests/chaos/wired_agent.py", str(self.agent_port), str(AGENT_DELAY_S)],
            self.env,
            "agent",
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                if httpx.get(f"{self.api_url}/healthz", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.3)
        raise RuntimeError("api did not start")

    def start_worker(self) -> subprocess.Popen[bytes]:
        p = self._spawn(["-m", "gauntlet_server.worker"], self.worker_env, "worker")
        self.workers.append(p)
        return p

    def start_workers(self) -> None:
        for _ in range(WORKERS):
            self.start_worker()

    def kill_random_worker(self, rng: random.Random) -> None:
        victim = rng.choice(self.workers)
        victim.send_signal(signal.SIGKILL)
        victim.wait()
        self.workers.remove(victim)
        self.kills += 1
        self.start_worker()

    def stop_workers(self) -> None:
        for w in self.workers:
            w.send_signal(signal.SIGTERM)
        for w in self.workers:
            try:
                w.wait(timeout=20)
            except subprocess.TimeoutExpired:
                w.kill()
        self.workers.clear()

    def stop_all(self) -> None:
        for p in self.procs:
            if p.poll() is None:
                p.kill()
                p.wait()


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    sys.path.insert(0, str(ROOT / "packages/server/tests/stores"))
    from pg_helpers import migrate_sync

    url = os.environ["TEST_DATABASE_URL"]
    migrate_sync(url, "upgrade", "head")

    async def wipe() -> None:
        eng = create_async_engine(url)
        async with eng.begin() as c:
            await c.execute(text("TRUNCATE workspaces CASCADE"))
        await eng.dispose()

    asyncio.run(wipe())
    tmp = tmp_path_factory.mktemp("chaos")
    st = Stack(tmp)
    st.start_core()
    yield st
    st.stop_all()


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(os.environ["TEST_DATABASE_URL"])
    yield eng
    await eng.dispose()


async def setup_docs(api: httpx.AsyncClient, agent_port: int) -> dict[str, str]:
    """Seed the pack, add a wired agent version and its suite; returns the ids to run."""
    seed = (await api.post("/v1/dev/seed", json={"reset": False}, timeout=120)).json()
    ver = await api.post(
        f"/v1/agents/{seed['agent_id']}/versions",
        json={
            "label": "wired",
            "target": {
                "kind": "openai_compat",
                "base_url": f"http://127.0.0.1:{agent_port}/v1",
                "model": "wired-agent",
                "wired": True,
            },
            "profile": {"purpose": "orders"},
            "world_id": "ecommerce",
        },
    )
    assert ver.status_code == 201, ver.text
    r = await api.post(
        "/v1/suites",
        json={"id": "suite_chaos_wired", "name": "wired", "scenarios": WIRED_SCENARIOS},
    )
    assert r.status_code == 201, r.text
    return {"hosted": seed["agent_version_id"], "wired": ver.json()["id"]}


async def make_runs(api: httpx.AsyncClient, versions: dict[str, str]) -> dict[str, str]:
    """A hosted run (smoke suite x reps) and a wired run; returns {label: run_id}."""
    out = {}
    for label, suite, reps in (
        ("hosted", "ecommerce_smoke", HOSTED_REPS),
        ("wired", "suite_chaos_wired", WIRED_REPS),
    ):
        r = await api.post(
            "/v1/runs",
            json={
                "suite_id": suite,
                "agent_version_id": versions[label],
                "repetitions": reps,
                "budget_usd_micros": 30_000_000,
                "seed": 11,
            },
        )
        assert r.status_code == 201, r.text
        out[label] = r.json()["id"]
    return out


async def wait_runs(api: httpx.AsyncClient, run_ids: list[str]) -> None:
    deadline = time.time() + DEADLINE_S
    while time.time() < deadline:
        statuses = [(await api.get(f"/v1/runs/{r}")).json()["status"] for r in run_ids]
        if all(s == "done" for s in statuses):
            return
        await asyncio.sleep(0.5)
    raise AssertionError(f"runs did not finish within {DEADLINE_S}s")


async def killer(stack: Stack, stop: asyncio.Event, rng: random.Random) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), KILL_EVERY_S)
        except TimeoutError:
            await asyncio.to_thread(stack.kill_random_worker, rng)


async def execute(
    stack: Stack, api: httpx.AsyncClient, versions: dict[str, str], *, chaos: bool, seed: int
) -> dict[str, str]:
    runs = await make_runs(api, versions)
    stack.start_workers()
    stop = asyncio.Event()
    task = asyncio.create_task(killer(stack, stop, random.Random(seed))) if chaos else None
    try:
        await wait_runs(api, list(runs.values()))
    finally:
        stop.set()
        if task:
            await task
        stack.stop_workers()
    return runs


def _scrub(doc: Any) -> Any:
    """Drop what legitimately differs between two runs of the same episode."""
    if isinstance(doc, dict):
        return {
            k: _scrub(v)
            for k, v in doc.items()
            if k not in {"id", "ts", "wall_ms", "latency_ms", "created_at"}
        }
    if isinstance(doc, list):
        return [_scrub(v) for v in doc]
    return doc


async def snapshot(engine: AsyncEngine, run_id: str) -> dict[str, Any]:
    async with engine.connect() as c:
        eps = (
            (
                await c.execute(
                    text(
                        "SELECT id, scenario_id, rep, status, outcome, termination, attempt, "
                        "next_seq, cost_usd_micros FROM episodes WHERE run_id = :r"
                    ),
                    {"r": run_id},
                )
            )
            .mappings()
            .all()
        )
        out: dict[str, Any] = {"episodes": {}, "problems": []}
        for ep in eps:
            key = f"{ep['scenario_id']}#{ep['rep']}"
            events = (
                await c.execute(
                    text("SELECT seq, doc FROM events WHERE episode_id = :e ORDER BY seq"),
                    {"e": ep["id"]},
                )
            ).all()
            seqs = [e.seq for e in events]
            if seqs != list(range(len(seqs))) or ep["next_seq"] != len(seqs):
                out["problems"].append(f"{key}: seq {seqs[:3]}..{seqs[-3:]} next={ep['next_seq']}")
            live_fx = (
                await c.execute(
                    text("SELECT key, status FROM effects WHERE episode_id = :e"), {"e": ep["id"]}
                )
            ).all()
            arch_fx = (
                await c.execute(
                    text("SELECT attempt, key, status FROM effects_archive WHERE episode_id = :e"),
                    {"e": ep["id"]},
                )
            ).all()
            keys = [f.key for f in live_fx]
            if len(keys) != len(set(keys)):
                out["problems"].append(f"{key}: duplicate live effect keys")
            for attempt in {a.attempt for a in arch_fx}:
                ak = [a.key for a in arch_fx if a.attempt == attempt]
                if len(ak) != len(set(ak)):
                    out["problems"].append(f"{key}: duplicate archived effect keys")
            out["episodes"][key] = {
                "status": ep["status"],
                "outcome": ep["outcome"],
                "termination": ep["termination"],
                "attempt": ep["attempt"],
                "events": [_scrub(e.doc) for e in events],
                "effects": sorted((f.key, f.status) for f in live_fx),
            }
        run = (
            (
                await c.execute(
                    text("SELECT spent_usd_micros, reserved_usd_micros FROM runs WHERE id = :r"),
                    {"r": run_id},
                )
            )
            .mappings()
            .one()
        )
        cost = (
            await c.execute(
                text(
                    "SELECT coalesce(sum((cost->>'usd_micros')::bigint), 0) FROM ("
                    " SELECT e.cost FROM effects e JOIN episodes p ON p.id = e.episode_id"
                    "  WHERE p.run_id = :r AND e.status = 'done'"
                    " UNION ALL"
                    " SELECT a.cost FROM effects_archive a JOIN episodes p ON p.id = a.episode_id"
                    "  WHERE p.run_id = :r AND a.status = 'done') x"
                ),
                {"r": run_id},
            )
        ).scalar_one()
        ep_cost = sum(e["cost_usd_micros"] for e in eps)
        out["spent"], out["reserved"] = run["spent_usd_micros"], run["reserved_usd_micros"]
        out["effect_cost"], out["episode_cost"] = int(cost), int(ep_cost)
        return out


def refunds(events: list[dict[str, Any]]) -> int:
    return sum(
        1
        for e in events
        if e.get("kind") == "tool_call" and (e.get("payload") or {}).get("tool") == "issue_refund"
    )


async def test_chaos_matches_clean_run(stack: Stack, engine: AsyncEngine) -> None:
    seed = int(os.environ.get("CHAOS_SEED") or time.time())
    print(f"chaos seed {seed}")
    async with httpx.AsyncClient(
        base_url=stack.api_url, headers={"Authorization": f"Bearer {KEY}"}, timeout=60
    ) as api:
        versions = await setup_docs(api, stack.agent_port)
        clean = await execute(stack, api, versions, chaos=False, seed=seed)
        chaos = await execute(stack, api, versions, chaos=True, seed=seed)
    print(f"workers killed: {stack.kills}")
    assert stack.kills >= 5, "the killer barely ran; the episodes were too fast"

    total = 0
    for label in ("hosted", "wired"):
        a, b = await snapshot(engine, clean[label]), await snapshot(engine, chaos[label])
        assert not a["problems"], a["problems"]
        assert not b["problems"], b["problems"]
        assert a["episodes"].keys() == b["episodes"].keys()
        total += len(b["episodes"])
        for key, ep in b["episodes"].items():
            ref = a["episodes"][key]
            assert ep["status"] == "done", (label, key, ep["status"])
            assert ep["outcome"] != "platform_error", (label, key)
            assert (ep["outcome"], ep["termination"]) == (ref["outcome"], ref["termination"]), key
            assert ep["events"] == ref["events"], (label, key, "journal differs from clean run")
            assert ep["effects"] == ref["effects"], (label, key)
            assert refunds(ep["events"]) == refunds(ref["events"]), (label, key)
        for snap in (a, b):
            assert snap["spent"] == snap["effect_cost"] == snap["episode_cost"], (label, snap)
            assert snap["reserved"] == 0, (label, "reservation leaked", snap["reserved"])
        refund_eps = [k for k in b["episodes"] if k.startswith("scn_ecom_01#")]
        assert refund_eps
        assert all(refunds(b["episodes"][k]["events"]) == 1 for k in refund_eps), label
    assert total == 60
