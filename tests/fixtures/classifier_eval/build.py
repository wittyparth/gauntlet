"""Deterministic evaluation corpus for the injection classifier (P4-4).

Positives: library attacks whose vector is `tool_result` or `document`, with placeholders
substituted by fixed fake values, embedded in benign document text from the packs (at most
300). Negatives: benign texts from the packs (document bodies, record text) plus 200 neutral
paragraphs from a seeded template over world data. No attack text is authored here.
"""

from __future__ import annotations

import random
from pathlib import Path

import yaml
from gauntlet_core.schema import Attack
from gauntlet_core.security import load_attacks
from gauntlet_core.security.placeholders import extract_placeholders, substitute
from gauntlet_core.security.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[3]
FAKE = {
    "marker": "ZX-4417",
    "attacker_email": "attacker@evil.example",
    "attacker_url": "https://evil.example/collect",
    "honeytool": "admin_export",
    "user_goal": "check my order",
}
MAX_POSITIVES = 300
NEUTRAL = 200


def pack_texts() -> list[str]:
    """Benign strings from every pack world: document bodies and long record fields."""
    out: list[str] = []
    for world in sorted((ROOT / "packs").glob("*/world*.yaml")) + sorted(
        (ROOT / "packs").glob("*/worlds/*.yaml")
    ):
        doc = yaml.safe_load(world.read_text()) or {}
        for d in doc.get("documents") or []:
            if not d.get("injection"):
                out.append(str(d["body"]))
        for rows in (doc.get("seed") or {}).values():
            for row in rows:
                out += [v for v in row.values() if isinstance(v, str) and len(v.split()) >= 5]
    return out


def attack_payloads(attacks: list[Attack]) -> list[str]:
    out: list[str] = []
    for a in attacks:
        if a.vector not in ("tool_result", "document"):
            continue
        for payload in [a.payload] if isinstance(a.payload, str) else a.payload:
            values = {n: FAKE.get(n, "x") for n in extract_placeholders(payload)}
            out.append(substitute(payload, values))
    return out


def neutral_paragraphs(seed: int, n: int = NEUTRAL) -> list[str]:
    rng = random.Random(seed)
    items = ["a tent", "a sleeping bag", "hiking boots", "a water filter", "a rain jacket"]
    sentences = [
        "Order {o} contains {i} and was packed on {d}.",
        "The customer asked when {i} would arrive and was given the tracking estimate.",
        "Returns for {i} are accepted within 30 days of delivery in original packaging.",
        "Shipping to {c} usually takes {n} business days.",
        "Please keep the receipt for {i}; it is needed for warranty claims.",
    ]
    cities = ["Oslo", "Denver", "Leeds", "Turin", "Perth"]
    out: list[str] = []
    for _ in range(n):
        parts = [
            rng.choice(sentences).format(
                o=f"ord_{rng.randint(1000, 9999)}",
                i=rng.choice(items),
                d=f"2026-0{rng.randint(1, 9)}-{rng.randint(10, 28)}",
                c=rng.choice(cities),
                n=rng.randint(2, 7),
            )
            for _ in range(rng.randint(2, 5))
        ]
        out.append(" ".join(parts))
    return out


def build(seed: int = 7) -> tuple[list[str], list[str]]:
    lib = load_attacks(ROOT / "attacks" / "library", load_taxonomy())
    rng = random.Random(seed)
    payloads = attack_payloads(lib.all())
    rng.shuffle(payloads)
    benign = pack_texts()
    positives = []
    for p in payloads[:MAX_POSITIVES]:
        ctx = rng.choice(benign) if benign else ""
        positives.append(f"{ctx}\n\n{p}" if rng.random() < 0.5 else f"{p}\n\n{ctx}")
    negatives = sorted(set(benign)) + neutral_paragraphs(seed)
    return positives, negatives


if __name__ == "__main__":
    pos, neg = build()
    print(f"{len(pos)} positives, {len(neg)} negatives")
