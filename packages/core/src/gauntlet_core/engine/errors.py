"""Engine exceptions. Each one maps to a specific recovery action in the runner."""

from __future__ import annotations


class EngineError(Exception):
    pass


class StaleLease(EngineError):
    """Another worker owns this episode now. Stop immediately, write nothing."""


class SeqConflict(EngineError):
    """Someone else appended to the journal (wired facade). Reload and continue."""


class NonDeterminism(EngineError):
    """Re-execution diverged from the journal. Always a platform bug (or, replaying a cassette
    under `verify_payloads`, the first point where the replay differs from the recording).

    `seq` is the journal position where the replay stood; `expected` and `got` describe the
    recorded and the produced side when known."""

    def __init__(
        self,
        message: str = "",
        *,
        seq: int | None = None,
        expected: object = None,
        got: object = None,
    ) -> None:
        super().__init__(message)
        self.seq, self.expected, self.got = seq, expected, got


class IndeterminateEffect(EngineError):
    """A non-retry-safe effect was in flight when the previous execution died.

    The runner abandons this attempt and starts the episode again from scratch.
    """


class BudgetExhausted(EngineError):
    """The run budget cannot cover the next effect."""


class PermanentEffectError(EngineError):
    """Raise from an effect function to record the failure so replay re-raises it.

    Any other exception leaves the effect `pending` (the execution is assumed to have died).
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message


class TargetError(PermanentEffectError):
    """The target agent could not be reached or returned an unusable reply."""
