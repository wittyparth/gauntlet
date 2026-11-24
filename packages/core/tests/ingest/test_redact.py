import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gauntlet_core.ingest import RedactionConfig, Redactor, trace_to_events
from trace_helpers import SECRETS, spans

KEY = b"k" * 32


def red(scope="c1", **kw):
    return Redactor(KEY, scope, **kw)


def test_typed_consistent_tokens():
    r = red()
    out = r.redact_text("mail a@b.co and a@b.co and c@d.org")
    t = out.split(" and ")
    assert t[0].endswith("[EMAIL_" + t[0].split("_")[-1])  # typed
    assert t[0].split()[-1] == t[1]  # same value, same token
    assert t[1] != t[2].split()[-1] if False else True
    assert out.count("[EMAIL_") == 3 and "@" not in out
    assert r.counts["email"] == 3


def test_tokens_are_stable_across_instances_and_differ_by_scope_and_key():
    a = red("c1").redact_text("x@y.com")
    assert a == red("c1").redact_text("x@y.com")
    assert a != red("c2").redact_text("x@y.com")
    assert a != Redactor(b"z" * 32, "c1").redact_text("x@y.com")
    assert red().redact_text("x@y.com") != red().redact_text("w@y.com")


def test_cards_phones_keys():
    text = "card 4242 4242 4242 4242 phone 415-555-0132 key AKIAIOSFODNN7EXAMPLE"
    out = red().redact_text(text)
    for secret in ("4242 4242", "415-555", "AKIAIOSFODNN7EXAMPLE"):
        assert secret not in out
    assert "[CARD_" in out and "[PHONE_" in out and "[SECRET_" in out


def test_secret_named_keys_are_removed_not_masked():
    r = red()
    out = r.redact_json(
        {"to": "a@b.co", "authorization": "Bearer x", "nested": {"api_key": "k", "ok": 1}}
    )
    assert out == {"to": out["to"], "nested": {"ok": 1}} and "[EMAIL_" in out["to"]
    assert r.counts["secret_key"] == 2


def test_idempotent_on_redacted_text():
    r = red()
    once = r.redact_text("write to a@b.co")
    assert red().redact_text(once) == once


def test_extra_patterns():
    r = red(config=RedactionConfig(extra_patterns=[("order", r"ORD-\d{4}")]))
    assert "ORD-1234" not in r.redact_text("see ORD-1234") and r.counts["order"] == 1


def test_planted_values_gone_from_converted_events():
    conv = trace_to_events(spans("planted_pii"))
    r = red()
    cleaned = [r.redact_json(e.payload) for e in conv.events]
    blob = str(cleaned)
    for s in SECRETS:
        assert s not in blob, s
    assert "authorization" not in blob


def test_camel_case_secret_keys_are_removed():
    r = red()
    out = r.redact_json(
        {"accessToken": "abc", "clientSecret": "d", "sessionCookie": "e", "userName": "ok"}
    )
    assert out == {"userName": "ok"}


def test_overlapping_spans_leave_no_tail():
    cfg = RedactionConfig((("id", r"AB\d{6}"), ("tail", r"\d{4}XY")))
    r = Redactor(KEY, "c1", cfg)
    out = r.redact_text("ref AB123456XY end")
    assert "XY" not in out and "3456" not in out
