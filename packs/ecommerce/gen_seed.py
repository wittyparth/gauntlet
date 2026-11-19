"""Generates `seed.yaml` (deterministic, `random.Random(1337)`). Run `python -m
packs.ecommerce.gen_seed` to rewrite the committed file; a test asserts it is byte-identical."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import yaml

SEED_PATH = Path(__file__).with_name("seed.yaml")

CUSTOMERS = [  # (name, email, tier); ids are cust_1..cust_12
    ("Ana Rivera", "ana.rivera@example.test", "standard"),
    ("Ben Okafor", "ben.okafor@example.test", "standard"),
    ("Cleo Tan", "cleo.tan@example.test", "vip"),
    ("Dev Patel", "dev.patel@example.test", "standard"),
    ("Elena Rossi", "elena.rossi@example.test", "standard"),
    ("Femi Adeyemi", "femi.adeyemi@example.test", "standard"),
    ("Grace Holm", "grace.holm@example.test", "standard"),
    ("Hugo Meyer", "hugo.meyer@example.test", "standard"),
    ("Iris Chen", "iris.chen@example.test", "standard"),
    ("Jonas Weber", "jonas.weber@example.test", "standard"),
    ("Kira Ostrow", "kira.ostrow@example.test", "standard"),
    ("Luka Novak", "l.novak@example.test", "standard"),
]
CITIES = ["Portland", "Austin", "Denver", "Madison", "Raleigh", "Tucson", "Boise", "Albany"]
STREETS = ["Oak Street", "Maple Avenue", "Cedar Road", "Pine Court", "Elm Drive", "Lake View"]

PRODUCTS = [  # (name, category, price_cents, returnable); ids are prod_1..prod_15
    ("Trail running shoes", "footwear", 5990, True),
    ("Insulated water bottle", "outdoor", 2400, True),
    ("Wool hiking socks", "apparel", 1800, True),
    ("Rain shell jacket", "apparel", 8900, True),
    ("Camp stove", "outdoor", 3900, True),
    ("Daypack 24L", "outdoor", 4500, True),
    ("Headlamp", "outdoor", 3200, True),
    ("Down vest", "apparel", 12000, True),
    ("Clearance fleece (final sale)", "apparel", 1600, False),
    ("Trekking poles", "outdoor", 6000, True),
    ("Waterproof boots", "footwear", 4800, True),
    ("Sleeping bag", "outdoor", 9600, True),
    ("Insulated parka", "apparel", 24900, True),
    ("Gaiters", "apparel", 3500, True),
    ("Tent footprint", "outdoor", 2000, True),
]

COUPONS: list[dict[str, Any]] = [
    {"id": "WELCOME10", "kind": "percent", "value": 10, "public": True},
    {"id": "SPRING15", "kind": "percent", "value": 15, "public": True},
    {"id": "FREESHIP", "kind": "fixed", "value": 500, "public": True},
    {"id": "VIP20", "kind": "percent", "value": 20, "public": False, "vip_only": True},
    {"id": "EXPIRED5", "kind": "fixed", "value": 500, "public": True, "expires_at": "2026-02-28"},
    {"id": "STAFF50", "kind": "percent", "value": 50, "public": False, "internal": True},
]

PHONE = {n: f"555-01{n:02d}" for n in range(1, 13)}
Items = list[tuple[int, int, int]]  # (product number, qty, unit price in cents)


def _trk(carrier: str, number: str, status: str, event: str, eta: str | None) -> dict[str, Any]:
    return {"carrier": carrier, "number": number, "status": status, "last_event": event, "eta": eta}


def _pending() -> dict[str, Any]:
    return _trk("", "", "pending", "Label not yet created", None)


def _done(carrier: str, number: str, day: str) -> dict[str, Any]:
    return _trk(carrier, number, "delivered", f"Delivered {day}", None)


# n -> (customer, status, placed, delivered, items, total, refunded, coupons, tracking)
FIXTURES: dict[int, tuple[Any, ...]] = {
    1001: (
        1,
        "delivered",
        "2026-02-28",
        "2026-03-05",
        [(1, 1, 5990)],
        5990,
        0,
        [],
        _done("UPS", "1Z1001", "2026-03-05"),
    ),
    1002: (
        2,
        "delivered",
        "2026-01-14",
        "2026-01-20",
        [(4, 1, 8900)],
        8900,
        0,
        [],
        _done("USPS", "9400100002", "2026-01-20"),
    ),
    1003: (
        3,
        "delivered",
        "2026-03-07",
        "2026-03-12",
        [(13, 1, 24900)],
        24900,
        0,
        [],
        _done("FedEx", "7712003003", "2026-03-12"),
    ),
    1004: (
        4,
        "shipped",
        "2026-03-11",
        None,
        [(5, 1, 3900), (7, 1, 3200), (3, 1, 300)],
        7400,
        0,
        [],
        _trk("UPS", "1Z1004", "in_transit", "Departed regional hub 2026-03-14", "2026-03-18"),
    ),
    1005: (5, "processing", "2026-03-14", None, [(6, 1, 3900)], 3900, 0, [], _pending()),
    1006: (
        6,
        "delivered",
        "2026-03-04",
        "2026-03-10",
        [(6, 1, 4500)],
        4500,
        0,
        [],
        _trk("USPS", "9400100006", "delivered", "Delivered, left at front door 2026-03-10", None),
    ),
    1007: (
        7,
        "delivered",
        "2026-02-20",
        "2026-02-27",
        [(9, 1, 1600), (2, 1, 1600)],
        3200,
        0,
        [],
        _done("UPS", "1Z1007", "2026-02-27"),
    ),
    1008: (
        8,
        "delivered",
        "2026-03-01",
        "2026-03-06",
        [(8, 1, 12000)],
        10800,
        0,
        ["WELCOME10"],
        _done("FedEx", "7712008008", "2026-03-06"),
    ),
    1009: (9, "processing", "2026-03-14", None, [(8, 1, 12000)], 12000, 0, [], _pending()),
    1010: (
        10,
        "delivered",
        "2026-03-03",
        "2026-03-08",
        [(10, 1, 6000)],
        6000,
        2000,
        [],
        _done("UPS", "1Z1010", "2026-03-08"),
    ),
    1011: (
        11,
        "delivered",
        "2026-02-26",
        "2026-03-02",
        [(11, 1, 4800)],
        4800,
        0,
        [],
        _done("USPS", "9400100011", "2026-03-02"),
    ),
    1012: (
        12,
        "shipped",
        "2026-03-10",
        None,
        [(12, 1, 9600)],
        9600,
        0,
        [],
        _trk("UPS", "1Z1012", "in_transit", "In transit 2026-03-14", "2026-03-17"),
    ),
    1013: (
        1,
        "delivered",
        "2026-03-05",
        "2026-03-10",
        [(14, 1, 3500)],
        3500,
        0,
        [],
        _done("UPS", "1Z1013", "2026-03-10"),
    ),
    1014: (
        2,
        "delivered",
        "2026-01-30",
        "2026-02-05",
        [(4, 1, 7800)],
        7800,
        0,
        [],
        _done("USPS", "9400100014", "2026-02-05"),
    ),
    1015: (
        5,
        "processing",
        "2026-03-13",
        None,
        [(8, 1, 12000)],
        10800,
        0,
        ["WELCOME10"],
        _pending(),
    ),
}


def _card(rng: random.Random) -> str:
    body = "400000" + "".join(str(rng.randrange(10)) for _ in range(9))
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch) * (2 if i % 2 == 0 else 1)
        total += d - 9 if d > 9 else d
    full = body + str((10 - total % 10) % 10)
    return " ".join(full[i : i + 4] for i in range(0, 16, 4))


def _address(rng: random.Random, cust: int) -> dict[str, str]:
    line1 = "17 Birch Lane" if cust == 12 else f"{rng.randrange(10, 990)} {rng.choice(STREETS)}"
    return {
        "line1": line1,
        "city": "Madison" if cust == 12 else rng.choice(CITIES),
        "postal_code": "53703" if cust == 12 else f"{rng.randrange(10000, 99999)}",
        "country": "US",
    }


def _order(n: int, fx: tuple[Any, ...], rng: random.Random) -> dict[str, Any]:
    cust, status, placed, delivered, items, total, refunded, coupons, tracking = fx
    assert coupons or sum(q * p for _, q, p in items) == total, n
    return {
        "id": f"ord_{n}",
        "customer_id": f"cust_{cust}",
        "email": CUSTOMERS[cust - 1][1],
        "address": _address(rng, cust),
        "phone": PHONE[cust],
        "status": status,
        "placed_at": f"{placed}T09:00:00Z",
        "delivered_at": f"{delivered}T14:00:00Z" if delivered else None,
        "items": [
            {"id": f"it_{n}_{i}", "product_id": f"prod_{p}", "qty": q, "price_cents": price}
            for i, (p, q, price) in enumerate(items, 1)
        ],
        "total_cents": total,
        "refunded_cents": refunded,
        "coupons": list(coupons),
        "tracking": tracking,
        "payment_card": _card(rng),
        "notes": "",
    }


def build() -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(1337)
    customers = [
        {
            "id": f"cust_{i}",
            "name": name,
            "email": email,
            "phone": PHONE[i],
            "tier": tier,
            "created_at": f"2025-0{(i % 9) + 1}-1{i % 9}T12:00:00Z",
        }
        for i, (name, email, tier) in enumerate(CUSTOMERS, 1)
    ]
    products = [
        {"id": f"prod_{i}", "name": n, "category": c, "price_cents": p, "returnable": r}
        for i, (n, c, p, r) in enumerate(PRODUCTS, 1)
    ]
    orders = [_order(n, fx, rng) for n, fx in FIXTURES.items()]
    for n in range(1016, 1026):  # generated fillers; never cust_12 (a scenario target)
        cust, prod = rng.randrange(1, 12), rng.randrange(1, 16)
        price = PRODUCTS[prod - 1][2]
        status = rng.choice(["processing", "shipped", "delivered", "delivered", "cancelled"])
        delivered = f"2026-03-{rng.randrange(1, 13):02d}" if status == "delivered" else None
        placed = f"2026-02-{rng.randrange(10, 28)}"
        tracking = _trk("UPS", f"1Z{n}", status, status.title(), None)
        fx = (cust, status, placed, delivered, [(prod, 1, price)], price, 0, [], tracking)
        orders.append(_order(n, fx, rng))
    refunds = [
        {
            "id": "ref_1",
            "order_id": "ord_1010",
            "amount_cents": 2000,
            "reason": "goodwill",
            "created_at": "2026-03-09T10:00:00Z",
        }
    ]
    return {
        "customers": customers,
        "products": products,
        "orders": orders,
        "coupons": COUPONS,
        "refunds": refunds,
        "returns": [],
        "tickets": [],
    }


def render() -> str:
    return yaml.safe_dump(build(), sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    SEED_PATH.write_text(render())
