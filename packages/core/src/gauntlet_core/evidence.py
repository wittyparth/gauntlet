"""Evidence pack container: a zip with `manifest.json`, content files, `SHA256SUMS` over every
other file, and an optional Ed25519 `SIGNATURE` over `SHA256SUMS`. Building and verifying use
only this module, so a pack verifies offline with nothing but the file (and, for the signature,
the public key published in the manifest or supplied by the verifier).

The wording of a pack is "evidence supporting"; nothing here certifies compliance."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .audit_chain import verify_rows

__all__ = [
    "AUDIT_EXCERPT",
    "SIGNATURE",
    "SUMS",
    "VerifyReport",
    "build_zip",
    "public_key_b64",
    "verify_pack",
]

SUMS = "SHA256SUMS"
SIGNATURE = "SIGNATURE"
MANIFEST = "manifest.json"
AUDIT_EXCERPT = "audit/excerpt.json"
_FIXED_DATE = (2020, 1, 1, 0, 0, 0)  # deterministic zip bytes


def _private(seed_b64: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(seed_b64))


def public_key_b64(seed_b64: str) -> str:
    raw = (
        _private(seed_b64)
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    return base64.b64encode(raw).decode()


def build_zip(files: Mapping[str, bytes], *, signing_seed_b64: str | None = None) -> bytes:
    """`files` must not contain `SHA256SUMS` or `SIGNATURE`. Entries are written in sorted
    order with a fixed timestamp so equal input gives equal bytes."""
    if SUMS in files or SIGNATURE in files:
        raise ValueError("SHA256SUMS and SIGNATURE are generated")
    sums = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {path}\n" for path, data in sorted(files.items())
    ).encode()
    out = dict(files)
    out[SUMS] = sums
    if signing_seed_b64:
        out[SIGNATURE] = base64.b64encode(_private(signing_seed_b64).sign(sums))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(out):
            info = zipfile.ZipInfo(path, _FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, out[path])
    return buf.getvalue()


@dataclass
class VerifyReport:
    ok: bool
    checksums: bool
    audit_chain: Literal["valid", "invalid", "absent"]
    signature: Literal["valid", "invalid", "absent", "unchecked"]
    files: int
    problems: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)


def verify_pack(data: bytes, *, public_key_b64_: str | None = None) -> VerifyReport:
    """Checksums for every file, the embedded audit-chain excerpt, and the signature. A pack
    signed but verified without a key reports `unchecked` unless the manifest carries one (a
    key from the manifest proves integrity, not who made the pack)."""
    problems: list[str] = []
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return VerifyReport(False, False, "absent", "absent", 0, ["not a zip file"])
    names = set(z.namelist())
    if SUMS not in names:
        return VerifyReport(False, False, "absent", "absent", len(names), ["no SHA256SUMS"])
    sums_raw = z.read(SUMS)
    listed: dict[str, str] = {}
    for line in sums_raw.decode().splitlines():
        digest, _, path = line.partition("  ")
        listed[path] = digest
    content = names - {SUMS, SIGNATURE}
    for path in sorted(content | set(listed)):
        if path not in listed:
            problems.append(f"{path}: not in SHA256SUMS")
        elif path not in names:
            problems.append(f"{path}: listed but missing")
        elif hashlib.sha256(z.read(path)).hexdigest() != listed[path]:
            problems.append(f"{path}: checksum mismatch")
    checksums = not problems

    manifest: dict[str, Any] = {}
    if MANIFEST in names:
        try:
            manifest = json.loads(z.read(MANIFEST))
        except ValueError:
            problems.append("manifest.json is not valid JSON")

    chain: Literal["valid", "invalid", "absent"] = "absent"
    if AUDIT_EXCERPT in names:
        try:
            doc = json.loads(z.read(AUDIT_EXCERPT))
            res = verify_rows(doc["rows"], anchor=doc.get("anchor_prev_hash"))
            chain = "valid" if res.ok else "invalid"
            if not res.ok:
                problems.append(f"audit chain broken at {res.first_bad_id}")
        except (ValueError, KeyError, TypeError):
            chain = "invalid"
            problems.append("audit excerpt unreadable")

    sig: Literal["valid", "invalid", "absent", "unchecked"] = "absent"
    if SIGNATURE in names:
        key_b64 = public_key_b64_ or manifest.get("public_key")
        if not key_b64:
            sig = "unchecked"
        else:
            try:
                pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(key_b64))
                pub.verify(base64.b64decode(z.read(SIGNATURE)), sums_raw)
                sig = "valid"
            except (InvalidSignature, ValueError):
                sig = "invalid"
                problems.append("signature does not verify")
    elif public_key_b64_:
        problems.append("a public key was given but the pack is unsigned")
        sig = "absent"

    ok = checksums and chain != "invalid" and sig not in ("invalid",) and not problems
    return VerifyReport(ok, checksums, chain, sig, len(names), problems, manifest)
