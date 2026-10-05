"""Public exceptions. Messages are intended to be actionable without a traceback."""

from typing import Any, Iterable


class RevletError(Exception):
    """Base class for engine errors."""


class OwnershipError(RevletError):
    """A call has missing or conflicting database ownership."""


class MutationError(RevletError):
    """A managed write was attempted in a read-only execution scope."""


class ReadOnlyError(RevletError, TypeError):
    """A write was attempted through a protected read interface."""


class StaleViewError(RevletError):
    """A borrowed view outlived its protected read state."""


class AdapterError(RevletError, TypeError):
    """A value or key cannot satisfy its adapter contract."""


class ClosedDatabaseError(RevletError):
    """An operation requires a database that has already been closed."""


class CancelledError(RevletError):
    """An execution request was cooperatively cancelled."""


class CycleError(RevletError):
    """A dependency cycle, with structured calls in traversal order."""

    def __init__(self, calls: Iterable[Any]) -> None:
        self.calls = tuple(calls)
        names = " -> ".join(call.name for call in self.calls)
        super().__init__("Dependency cycle: {}. Supply an explicit cycle solver.".format(names))
