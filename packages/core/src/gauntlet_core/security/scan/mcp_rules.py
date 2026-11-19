"""MCP scanner rules MCP-001..MCP-011 over a `tools/list` result (pure; no I/O).

The rules match shapes (patterns, structure), not specific wording. MCP-012 is reserved for pin
mismatch (rug pull, P4-3).
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from collections import Counter
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from gauntlet_core.checks.detectors.secret import detect_secret

from .types import ScanFinding, Severity, TransportInfo, excerpt

__all__ = ["MCP_RULES", "scan_mcp_tools"]

MCP_RULES: dict[str, tuple[str, str]] = {
    "MCP-001": ("Hidden instructions to the model", "mcp"),
    "MCP-002": ("Invisible or bidirectional Unicode characters", "mcp"),
    "MCP-003": ("Cross-tool reference (shadowing)", "mcp"),
    "MCP-004": ("Tool name collision or confusable", "mcp"),
    "MCP-005": ("Over-broad string parameter", "tool_injection"),
    "MCP-006": ("Risky tool without annotations", "excessive_agency"),
    "MCP-007": ("Description anomaly", "mcp"),
    "MCP-008": ("Secret in metadata", "data_disclosure"),
    "MCP-009": ("Unauthenticated remote server", "mcp"),
    "MCP-010": ("Cleartext transport", "mcp"),
    "MCP-011": ("Large attack surface", "excessive_agency"),
}

_INSTRUCTION = [
    re.compile(r"(?i)ignore (all |any )?(previous|prior|above) instructions"),
    re.compile(r"<IMPORTANT>|<SYSTEM>|\[INST\]"),
    re.compile(r"(?i)do not (tell|mention|inform|reveal)[^.]{0,40}(user|human)"),
    re.compile(r"(?i)before (using|calling) this tool[^.]{0,80}(read|send|fetch|open|include)"),
    re.compile(r"(?i)without (telling|informing|notifying)"),
]
_CREDENTIAL = re.compile(r"(?i)(~/)?\.ssh|id_rsa|\.env\b|credentials")
_STRONG_PATH = re.compile(r"(?i)(~/)?\.ssh|id_rsa|\.env\b")
_INVISIBLE_RANGES = (
    (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064), (0x2066, 0x2069),
    (0xFEFF, 0xFEFF), (0xE0000, 0xE007F),
)  # fmt: skip


def _find_invisible(text: str) -> int | None:
    for i, ch in enumerate(text):
        if any(lo <= ord(ch) <= hi for lo, hi in _INVISIBLE_RANGES):
            return i
    return None


_SHADOW = re.compile(
    r"(?i)instead of|override|replace the .{0,40} tool|when (using|calling) the .{0,40} tool"
)
_INVOKE = re.compile(r"(?i)\b(call|use|invoke|run|execute|send|forward)\b")
_BASE64 = re.compile(r"[A-Za-z0-9+/]{64,}={0,2}")
_URL = re.compile(r"https?://([^\s/)\"'>]+)")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_RISKY = re.compile(r"(?i)delete|drop|remove|exec|run|write|send|transfer|pay")
_WELL_KNOWN = {"read_file", "bash", "execute_command", "web_search", "send_email"}
_PARAM_NAMES = {
    "command", "cmd", "shell", "script", "code", "sql", "query", "expression", "eval",
    "path", "file_path", "url", "uri",
}  # fmt: skip
_HIGH_PARAMS = {"command", "shell", "code", "sql", "eval"}


def _strings(obj: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(k, f"{path}.{k}") if isinstance(k, str) else ()
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, f"{path}[{i}]")


def _items(listing: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """(location, kind, item) for tools, resources and prompts."""
    out: list[tuple[str, str, dict[str, Any]]] = []
    for kind in ("tools", "resources", "prompts"):
        for it in listing.get(kind) or []:
            if isinstance(it, dict):
                name = str(it.get("name") or it.get("uri") or "?")
                out.append((name if kind == "tools" else f"{kind[:-1]}:{name}", kind, it))
    return out


def _levenshtein_one(a: str, b: str) -> bool:
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long = sorted((a, b), key=len)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))


def _loopback(host: str) -> bool:
    host = host.split(":")[0].strip("[]") if not host.startswith("[") else host.strip("[]")
    if host in {"localhost", ""}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _f(rule: str, sev: Severity, detail: str, loc: str, ev: str) -> ScanFinding:
    title, cat = MCP_RULES[rule]
    return ScanFinding(rule, sev, title, detail, loc, excerpt(ev, 0, 120), cat)


def _per_item(listing: dict[str, Any]) -> list[ScanFinding]:
    items = _items(listing)
    tool_names = [str(it.get("name", "")) for loc, kind, it in items if kind == "tools"]
    out: list[ScanFinding] = []
    for loc, kind, it in items:
        strs = list(_strings(it))
        blob = "\n".join(s for _, s in strs)
        # MCP-001
        first = next(((m, rx) for rx in _INSTRUCTION if (m := rx.search(blob))), None)
        cred = _CREDENTIAL.search(blob)
        if first is not None:
            sev: Severity = "critical" if cred else "high"
            out.append(_f("MCP-001", sev, "instruction-like text aimed at the model", loc,
                          blob[first[0].start():]))  # fmt: skip
        elif _STRONG_PATH.search(blob):
            m = _STRONG_PATH.search(blob)
            assert m is not None
            out.append(
                _f("MCP-001", "high", "reference to credential files", loc, blob[m.start() :])
            )
        # MCP-002
        for p, s in strs:
            i = _find_invisible(s)
            if i is not None:
                cp = f"U+{ord(s[i]):04X}"
                out.append(_f("MCP-002", "high", f"invisible character {cp} in {p}", loc,
                              ascii(s[max(0, i - 20): i + 20])))  # fmt: skip
                break
        desc = str(it.get("description") or "")
        # MCP-003
        if kind == "tools":
            others = [n for n in tool_names if n and n != it.get("name")]
            ref = next(
                (n for n in others if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", desc)), None
            )
            rx_hit = _SHADOW.search(desc)
            if ref or rx_hit:
                invoke = bool(_INVOKE.search(desc))
                sev = "high" if invoke and ref else "medium"
                out.append(_f("MCP-003", sev, f"references {ref or 'another tool'}", loc, desc))
        # MCP-007
        if len(desc) > 2000:
            out.append(
                _f("MCP-007", "medium", f"description has {len(desc)} characters", loc, desc)
            )
        if _BASE64.search(desc):
            out.append(_f("MCP-007", "medium", "base64-like run in description", loc, desc))
        for m in _URL.finditer(desc):
            if not _loopback(m.group(1)):
                out.append(_f("MCP-007", "medium", "external URL in description", loc, m.group(0)))
                break
        img = _IMAGE.search(desc)
        if img:
            out.append(_f("MCP-007", "high", "markdown image syntax (exfiltration vector)", loc,
                          img.group(0)))  # fmt: skip
        # MCP-008
        for p, s in strs:
            hits = detect_secret(s)
            if hits:
                out.append(_f("MCP-008", "high", f"{hits[0].label} in {p}", loc, hits[0].quote))
                break
        if kind == "tools":
            out += _tool_only(loc, it, desc)
    return out


def _tool_only(loc: str, it: dict[str, Any], desc: str) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    props = (it.get("inputSchema") or {}).get("properties") or {}
    for pname, spec in props.items():
        if not isinstance(spec, dict) or spec.get("type") != "string":
            continue
        if pname.lower() in _PARAM_NAMES and not (
            spec.get("enum") or spec.get("pattern") or spec.get("maxLength")
        ):
            sev: Severity = "high" if pname.lower() in _HIGH_PARAMS else "medium"
            out.append(_f("MCP-005", sev, f"parameter {pname!r} accepts any string", loc, pname))
    ann = it.get("annotations") or {}
    if _RISKY.search(f"{it.get('name', '')} {desc}") and not (
        "destructiveHint" in ann or "readOnlyHint" in ann
    ):
        out.append(_f("MCP-006", "low", "no destructiveHint or readOnlyHint", loc, desc or loc))
    return out


def _names(listing: dict[str, Any]) -> list[ScanFinding]:
    names = [str(t.get("name", "")) for t in listing.get("tools") or [] if isinstance(t, dict)]
    out: list[ScanFinding] = []
    for n, c in Counter(names).items():
        if c > 1:
            out.append(_f("MCP-004", "medium", f"duplicate tool name ({c}x)", n, n))
    by_key: dict[str, set[str]] = {}
    for n in set(names):
        by_key.setdefault(unicodedata.normalize("NFKC", n).casefold(), set()).add(n)
    for group in by_key.values():
        if len(group) > 1:
            ev = " / ".join(ascii(g) for g in sorted(group))
            out.append(
                _f("MCP-004", "medium", "names equal after NFKC and casefold", sorted(group)[0], ev)
            )
    uniq = sorted(set(names))
    for i, a in enumerate(uniq):
        for b in uniq[i + 1 :]:
            if _levenshtein_one(a, b):
                out.append(_f("MCP-004", "medium", f"one edit away from {a!r}", b, f"{a} / {b}"))
    for n in uniq:
        if n in _WELL_KNOWN:
            out.append(_f("MCP-004", "medium", "name of a well-known tool", n, n))
    return out


def _transport(t: TransportInfo) -> list[ScanFinding]:
    out: list[ScanFinding] = []
    if t.kind != "http" or not t.url:
        return out
    parts = urlparse(t.url)
    loop = _loopback(parts.netloc.rsplit("@", 1)[-1])
    if t.connected_without_auth and not t.has_credentials:
        out.append(_f("MCP-009", "low" if loop else "high", "tools/list worked with no credentials",
                      t.url, t.url))  # fmt: skip
    if parts.scheme == "http" and not loop:
        out.append(_f("MCP-010", "high", "http:// to a non-loopback host", t.url, t.url))
    return out


def scan_mcp_tools(
    listing: dict[str, Any], *, transport: TransportInfo | None = None
) -> list[ScanFinding]:
    out = _per_item(listing) + _names(listing)
    tools = listing.get("tools") or []
    if len(tools) > 50:
        out.append(
            _f("MCP-011", "low", f"{len(tools)} tools in one server", "server", str(len(tools)))
        )
    out += _transport(transport or TransportInfo())
    return out
