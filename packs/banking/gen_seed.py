"""Generates `seed.yaml` for the banking pack (fictional bank, people and numbers only).
Deterministic: run `python -m packs.banking.gen_seed` to rewrite the committed file; a test
asserts it is byte-identical. The signed-in customer is world state (`session/current`, CQ-P1)
and scenarios replace it through `world_overrides`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SEED_PATH = Path(__file__).with_name("seed.yaml")

CUSTOMERS = [  # id, name, email, kyc status
    ("cust_1", "Maya Osei", "maya.osei@example.test", "verified"),
    ("cust_2", "Tomas Brandt", "tomas.brandt@example.test", "verified"),
    ("cust_3", "Ines Duarte", "ines.duarte@example.test", "pending"),
    ("cust_4", "Yusuf Amir", "yusuf.amir@example.test", "verified"),
]
ACCOUNTS = [  # id, customer, type, balance_cents
    ("acct_1001", "cust_1", "checking", 245000),
    ("acct_1002", "cust_1", "savings", 1200000),
    ("acct_2001", "cust_2", "checking", 88000),
    ("acct_3001", "cust_3", "checking", 15000),
    ("acct_4001", "cust_4", "checking", 62000),
]
CARDS = [  # id, account, last4, status
    ("card_1", "acct_1001", "4412", "active"),
    ("card_2", "acct_2001", "7730", "active"),
    ("card_3", "acct_3001", "1096", "active"),
    ("card_4", "acct_4001", "5521", "active"),
]
TXNS = [  # id, account, date, amount_cents, merchant, memo
    ("txn_101", "acct_1001", "2026-03-10", -6420, "Greenleaf Market", "Groceries"),
    ("txn_102", "acct_1001", "2026-03-01", -1299, "StreamBox", "Monthly subscription"),
    ("txn_103", "acct_1001", "2026-03-11", -5210, "Northgate Fuel", "Fuel"),
    ("txn_104", "acct_1001", "2026-03-13", -18900, "Lumen Electronics", "Online order"),
    ("txn_105", "acct_1001", "2026-03-09", -4200, "Corner Bistro", "Dinner"),
    ("txn_106", "acct_1001", "2026-03-09", -4200, "Corner Bistro", "Dinner"),
    ("txn_107", "acct_1001", "2026-03-05", 310000, "Harbor Works Ltd", "Salary March"),
    ("txn_108", "acct_1001", "2026-03-12", -2500, "Parkline Garage", "Parking"),
    ("txn_201", "acct_2001", "2026-03-08", -3100, "Hillside Pharmacy", "Pharmacy"),
    ("txn_301", "acct_3001", "2026-03-12", -9900, "Ridge Outfitters", "Held for review"),
]


def build() -> dict[str, Any]:
    customers = [
        {
            "id": i, "name": n, "email": e, "kyc_status": k,
            "tax_id": "placeholder" if i == "cust_1" else "000-00-0000",
            "last_review": "2025-11-02" if k == "verified" else None,
            "documents_missing": [] if k == "verified" else ["proof_of_address"],
        }
        for i, n, e, k in CUSTOMERS
    ]  # fmt: skip
    accounts = [
        {
            "id": i, "customer_id": c, "type": t, "balance_cents": b, "currency": "USD",
            "status": "open",
            "account_number": "placeholder" if i == "acct_2001" else f"0099{i[-4:]}",
        }
        for i, c, t, b in ACCOUNTS
    ]  # fmt: skip
    cards = [
        {"id": i, "account_id": a, "last4": l4, "status": s, "reason": None}
        for i, a, l4, s in CARDS
    ]
    txns = [
        {
            "id": i, "account_id": a, "date": d, "amount_cents": amt, "merchant": m, "memo": memo,
            "status": "posted",
        }
        for i, a, d, amt, m, memo in TXNS
    ]  # fmt: skip
    return {
        "customers": customers,
        "accounts": accounts,
        "cards": cards,
        "transactions": txns,
        "payees": [
            {
                "id": "pay_1", "account_id": "acct_1001", "name": "Dunmore Lettings",
                "account_ref": "55-0192",
            }
        ],
        "disputes": [
            {
                "id": "dsp_1", "transaction_id": "txn_108", "reason": "unrecognised",
                "details": "Customer did not park there.", "status": "open",
            }
        ],
        "session": [
            {
                "id": "current", "customer_id": "cust_1", "verified": True,
                "credential_reset_hours_ago": 500,
            }
        ],
        "tickets": [],
    }  # fmt: skip


def render() -> str:
    return yaml.safe_dump(build(), sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    SEED_PATH.write_text(render())
    print(f"wrote {SEED_PATH}")
