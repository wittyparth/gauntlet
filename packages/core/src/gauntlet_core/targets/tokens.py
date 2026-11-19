"""Episode tokens for the mock facade: `ep_id.epoch.sig`, HMAC-SHA256, base64url."""

from __future__ import annotations

import base64
import hashlib
import hmac

__all__ = ["mint_token", "verify_token"]


def _sig(episode_id: str, epoch: int, secret: bytes) -> str:
    mac = hmac.new(secret, f"{episode_id}.{epoch}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def mint_token(episode_id: str, epoch: int, secret: bytes) -> str:
    return f"{episode_id}.{epoch}.{_sig(episode_id, epoch, secret)}"


def verify_token(token: str, secret: bytes) -> tuple[str, int]:
    """Return (episode_id, epoch) or raise ValueError. Episode ids may contain dots."""
    try:
        rest, sig = token.rsplit(".", 1)
        episode_id, epoch_s = rest.rsplit(".", 1)
        epoch = int(epoch_s)
    except ValueError as e:
        raise ValueError("malformed token") from e
    if not hmac.compare_digest(sig, _sig(episode_id, epoch, secret)):
        raise ValueError("bad signature")
    return episode_id, epoch
