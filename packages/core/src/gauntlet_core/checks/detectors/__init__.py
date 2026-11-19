"""Deterministic detectors and their registry (CQ-B4).

Importing this package registers the six built-in detectors.
"""

from .adapters import register_all
from .commitment import detect_commitment_phrase
from .loop import detect_loop
from .markdown_exfil import detect_markdown_image_exfil
from .pii import ALL_KINDS, detect_pii
from .profanity import detect_profanity
from .registry import DetectorFn, get, names, register, text_detector
from .secret import detect_secret
from .types import Hit

register_all()

__all__ = [
    "ALL_KINDS",
    "DetectorFn",
    "Hit",
    "detect_commitment_phrase",
    "detect_loop",
    "detect_markdown_image_exfil",
    "detect_pii",
    "detect_profanity",
    "detect_secret",
    "get",
    "names",
    "register",
    "register_all",
    "text_detector",
]
