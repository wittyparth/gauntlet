"""Export blind review items for the L-R3 judge-agreement study.

Items (transcript, goal, rubric) come from the review API WITHOUT the judge verdict and go to
studies/data/l_r3_items_<rubric>.jsonl. Judge verdicts go to a separate file,
studies/data/l_r3_judge_<rubric>.jsonl, which the grader must not open until grading is done.

The review API reveals a verdict only after the caller posted a label (which writes a `human`
verdict into the product and changes episode outcomes), so verdicts are read with a read-only
transaction from the stack's Postgres instead.

The admin key is read in-process from .demo/stack.vars and never printed or written.

Usage: uv run python studies/export_review_items.py RUBRIC [--limit 100]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
BASE = "http://localhost:8088/v1"
PG = ["docker", "exec", "gauntletprod-postgres-1", "psql", "-U", "gauntlet", "-d", "gauntlet"]


def _key() -> str:
    for line in (ROOT / ".demo" / "stack.vars").read_text().splitlines():
        if line.startswith("GAUNTLET_ADMIN_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("admin key line not found")


def _get(path: str, key: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def _judge_rows(rubric: str, ids: list[str]) -> list[dict]:
    """Latest non-human verdict per episode (what get_item(reveal=true) would return)."""
    assert re.fullmatch(r"[a-z_]+", rubric)
    assert all(re.fullmatch(r"[A-Za-z0-9_\-]+", i) for i in ids)
    id_list = ",".join(f"'{i}'" for i in ids)
    sql = (
        "SELECT row_to_json(t) FROM (SELECT DISTINCT ON (episode_id) episode_id, "
        "result, doc FROM verdicts "
        f"WHERE criterion = '{rubric}' AND episode_id IN ({id_list}) "
        "AND doc->>'stage' <> 'human' ORDER BY episode_id, created_at DESC) t"
    )
    out = subprocess.run(
        [*PG, "-At", "-c", "BEGIN READ ONLY", "-c", sql, "-c", "COMMIT"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [json.loads(ln) for ln in out.splitlines() if ln.startswith("{")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rubric")
    ap.add_argument("--limit", type=int, default=100)
    a = ap.parse_args()
    key = _key()
    queue = _get(f"/review/queue?rubric={a.rubric}&limit={a.limit}", key)
    DATA.mkdir(exist_ok=True)
    items_path = DATA / f"l_r3_items_{a.rubric}.jsonl"
    with items_path.open("w") as f:
        for q in queue["items"]:
            it = _get(f"/review/items/{q['episode_id']}/{a.rubric}", key)
            assert it.get("judge") is None  # blind
            rec = {
                "episode_id": it["episode_id"], "rubric_id": a.rubric,
                "scenario_id": it["scenario_id"], "scenario_title": it["scenario_title"],
                "goal": it["goal"], "queue_reason": q["reason"],
                "rubric": it["rubric"], "transcript": it["transcript"],
            }  # fmt: skip
            f.write(json.dumps(rec) + "\n")
    judge = _judge_rows(a.rubric, [q["episode_id"] for q in queue["items"]])
    with (DATA / f"l_r3_judge_{a.rubric}.jsonl").open("w") as f:
        for j in judge:
            f.write(json.dumps(j) + "\n")
    print(f"{len(queue['items'])} items -> {items_path.name}; {len(judge)} judge rows (sealed)")


if __name__ == "__main__":
    main()
