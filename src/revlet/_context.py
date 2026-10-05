"""Execution-local state; no default database or process-wide memo storage."""

import asyncio
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional, Tuple

from ._errors import AdapterError, CancelledError

FRAME: ContextVar[Any] = ContextVar("revlet_frame", default=None)
CALLBACK: ContextVar[Optional[str]] = ContextVar("revlet_callback", default=None)
CANCELLATION: ContextVar[Tuple[Any, ...]] = ContextVar("revlet_cancellation", default=())
SOLVING: ContextVar[Any] = ContextVar("revlet_solving", default=None)


def execution_identity() -> Tuple[int, Any]:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.get_ident(), task


def current_frame() -> Any:
    frame = FRAME.get()
    if frame is not None and frame.active and frame.owner == execution_identity():
        return frame
    return None


def check_callback() -> None:
    name = CALLBACK.get()
    if name is not None:
        raise AdapterError("{} must not read tracked state or call queries.".format(name))


@contextmanager
def callback_scope(name: str) -> Iterator[None]:
    token = CALLBACK.set(name)
    try:
        yield
    finally:
        CALLBACK.reset(token)


class CancellationToken:
    """Thread-safe cancellation with optional parent composition."""

    def __init__(self, parent: Optional["CancellationToken"] = None) -> None:
        self._event = threading.Event()
        self._parent = parent

    @property
    def cancelled(self) -> bool:
        return self._event.is_set() or (self._parent is not None and self._parent.cancelled)

    def cancel(self) -> None:
        self._event.set()

    def check(self) -> None:
        if self.cancelled:
            raise CancelledError("The execution request was cancelled.")

    @contextmanager
    def scope(self) -> Iterator["CancellationToken"]:
        token = CANCELLATION.set(CANCELLATION.get() + (self,))
        try:
            self.check()
            yield self
        finally:
            CANCELLATION.reset(token)


def check_cancelled() -> None:
    """Cooperative checkpoint for Python loops and native integrations."""
    for token in CANCELLATION.get():
        token.check()
