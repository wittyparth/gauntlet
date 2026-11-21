"""`gauntlet run --remote`: create, poll on a fast clock, time out."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from cli_helpers import invoke
from gauntlet_cli.commands import remote

API = "http://host.test/api"


def run_doc(status: str, done: int = 0, label: str = "main", rid: str = "run_1") -> dict:
    return {
        "id": rid,
        "status": status,
        "spent_usd_micros": 12_000,
        "counts": {"total": 4, "done": done, "cancelled": 0, "queued": 0, "leased": 0,
                   "by_outcome": {}},
        "manifest": {"agent_version": {"label": label}},
    }  # fmt: skip


class Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(remote, "_now", c.now)
    monkeypatch.setattr(remote, "_sleep", c.sleep)
    return c


ARGS = ["run", "--remote", "--api-url", API, "--api-key", "gk_x", "--suite", "suite_1",
        "--agent-version", "agv_1"]  # fmt: skip


@respx.mock
def test_creates_polls_until_done_and_prints_the_url(runner, clock):
    create = respx.post(f"{API}/v1/runs").mock(
        return_value=httpx.Response(201, json=run_doc("queued"))
    )
    respx.get(f"{API}/v1/runs/run_1").mock(
        side_effect=[
            httpx.Response(200, json=run_doc("running", 2)),
            httpx.Response(200, json=run_doc("done", 4)),
        ]
    )
    res = invoke(runner, [*ARGS, "--reps", "3", "--budget-usd", "1.5", "--json"])
    assert res.exit_code == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["status"] == "done" and out["url"] == "http://host.test/runs/run_1"
    body = json.loads(create.calls.last.request.content)
    assert body == {"suite_id": "suite_1", "agent_version_id": "agv_1", "repetitions": 3,
                    "budget_usd_micros": 1_500_000, "adaptive": False}  # fmt: skip
    assert create.calls.last.request.headers["authorization"] == "Bearer gk_x"
    assert clock.sleeps == [5.0, 5.0]
    assert "2/4 episodes, spent $0.0120" in res.stderr


@respx.mock
def test_timeout_exits_3_and_leaves_the_run_going(runner, clock):
    respx.post(f"{API}/v1/runs").mock(return_value=httpx.Response(201, json=run_doc("queued")))
    respx.get(f"{API}/v1/runs/run_1").mock(
        return_value=httpx.Response(200, json=run_doc("running", 1))
    )
    res = invoke(runner, [*ARGS, "--timeout-min", "1"])
    assert res.exit_code == 3 and "keeps going" in res.stderr
    assert clock.t >= 60 and "run: run_1" in res.stdout
    assert not any(
        r.request.method == "POST" and "cancel" in str(r.request.url) for r in respx.calls
    )


@respx.mock
def test_failed_or_cancelled_run_exits_3(runner, clock):
    respx.post(f"{API}/v1/runs").mock(return_value=httpx.Response(201, json=run_doc("queued")))
    respx.get(f"{API}/v1/runs/run_1").mock(
        return_value=httpx.Response(200, json=run_doc("cancelled"))
    )
    assert invoke(runner, ARGS).exit_code == 3


@respx.mock
def test_no_wait_returns_right_after_creation(runner, clock):
    respx.post(f"{API}/v1/runs").mock(return_value=httpx.Response(201, json=run_doc("queued")))
    res = invoke(runner, [*ARGS, "--no-wait"])
    assert res.exit_code == 0 and clock.sleeps == []


@respx.mock
def test_auto_baseline_picks_latest_run_with_the_label(runner, clock):
    respx.get(f"{API}/v1/runs").mock(
        return_value=httpx.Response(
            200,
            json={"items": [run_doc("done", rid="run_feature", label="feat"),
                            run_doc("done", rid="run_main", label="main")],
                  "next_cursor": None},
        )
    )  # fmt: skip
    create = respx.post(f"{API}/v1/runs").mock(
        return_value=httpx.Response(201, json=run_doc("done"))
    )
    res = invoke(runner, [*ARGS, "--baseline", "auto", "--no-wait"])
    assert res.exit_code == 0, res.stderr
    assert json.loads(create.calls.last.request.content)["baseline_run_id"] == "run_main"
    listing = next(r for r in respx.calls if r.request.method == "GET").request.url.params
    assert listing["suite_id"] == "suite_1" and listing["status"] == "done"


@respx.mock
def test_server_rejection_exits_2_and_usage_errors_exit_2(runner, clock):
    respx.post(f"{API}/v1/runs").mock(
        return_value=httpx.Response(
            404, json={"error": {"code": "not_found", "message": "no suite"}}
        )
    )
    res = invoke(runner, ARGS)
    assert res.exit_code == 2 and "not_found" in res.stderr
    assert invoke(runner, ["run", "--remote", "--api-url", API]).exit_code == 2
    assert invoke(runner, ["run"]).exit_code == 2


def test_web_url_override_and_default():
    assert remote.web_url_for("https://x.io/api/", None) == "https://x.io"
    assert remote.web_url_for("https://x.io", None) == "https://x.io"
    assert remote.web_url_for("https://x.io/api", "https://web.io/") == "https://web.io"
