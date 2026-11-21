"""The runtime gateway as a Python SDK (P4-2): wrap an agent's tools and output, decide with
the L8 policy engine, record every decision."""

from . import classifier  # noqa: F401  (registers the injection_classifier detector)
from .approvals import ApprovalHandler, CallbackApprovals, HttpApprovals
from .decision import ApprovalInfo, DecisionRecord
from .errors import ApprovalExpired, NoActiveSession, PolicyBlocked
from .guard import Guard
from .session import Session
from .sinks import DecisionSink, HttpSink, JsonlSink, MemorySink

__all__ = [
    "ApprovalExpired",
    "ApprovalHandler",
    "ApprovalInfo",
    "CallbackApprovals",
    "DecisionRecord",
    "DecisionSink",
    "Guard",
    "HttpApprovals",
    "HttpSink",
    "JsonlSink",
    "MemorySink",
    "NoActiveSession",
    "PolicyBlocked",
    "Session",
]
