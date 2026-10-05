"""Public read interfaces; runtime implementations require only Python 3.9."""

from collections.abc import Callable, Iterable, Mapping, Sequence, Set
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, Concatenate, NamedTuple, Self, overload

type _Scalar = bool | int | float | complex | str | bytes | range | None
type _ExitType = type[BaseException] | None
type _ExitValue = BaseException | None
type _ExitTrace = TracebackType | None

__all__ = [
    "AdapterError",
    "CacheInfo",
    "CancellationToken",
    "CancelledError",
    "ClosedDatabaseError",
    "CycleContext",
    "CycleError",
    "Database",
    "DependencyToken",
    "Input",
    "MutationError",
    "OwnershipError",
    "QueryCall",
    "ReadGuard",
    "ReadOnlyError",
    "RevletError",
    "StaleViewError",
    "Tracked",
    "ValueAdapter",
    "check_cancelled",
    "copy_value",
    "tracked",
]

class RevletError(Exception): ...
class OwnershipError(RevletError): ...
class MutationError(RevletError): ...
class ReadOnlyError(RevletError, TypeError): ...
class StaleViewError(RevletError): ...
class AdapterError(RevletError, TypeError): ...
class ClosedDatabaseError(RevletError): ...
class CancelledError(RevletError): ...

class CycleError(RevletError):
    calls: tuple[QueryCall, ...]
    def __init__(self, calls: Iterable[QueryCall]) -> None: ...

class CacheInfo(NamedTuple):
    revision: int
    entries: int
    nodes: int
    hits: int
    validations: int
    executions: int
    evictions: int

class CancellationToken:
    def __init__(self, parent: CancellationToken | None = None) -> None: ...
    @property
    def cancelled(self) -> bool: ...
    def cancel(self) -> None: ...
    def check(self) -> None: ...
    def scope(self) -> AbstractContextManager[CancellationToken]: ...

def check_cancelled() -> None: ...
def copy_value(value: object, memo: dict[int, Any] | None = None) -> Any: ...

class ReadGuard:
    def __init__(self, db: Database, source: object = None) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: _ExitType, exc: _ExitValue, tb: _ExitTrace) -> None: ...
    def protect(self, value: object) -> Any: ...

class ValueAdapter[ValueT, ReadT]:
    stable: bool
    @classmethod
    def __class_getitem__(cls, parameters: Any) -> Any: ...
    def read(self, value: ValueT, guard: ReadGuard) -> ReadT: ...
    def edit(self, value: ValueT) -> AbstractContextManager[ValueT]: ...
    def equivalent(self, old: ReadT, new: ReadT) -> bool: ...

class Input[ReadT, WriteT]:
    @classmethod
    def __class_getitem__(cls, parameters: Any) -> Any: ...
    def __init__(
        self,
        database: Database,
        value: WriteT,
        *,
        adapter: ValueAdapter[WriteT, ReadT] | None = None,
    ) -> None: ...
    @property
    def database(self) -> Database: ...
    @property
    def changed_at(self) -> int: ...
    @property
    def value(self) -> ReadT: ...
    @value.setter
    def value(self, value: WriteT) -> None: ...
    def edit(self) -> AbstractContextManager[WriteT]: ...

class DependencyToken:
    name: str | None
    def __init__(self, database: Database, *, name: str | None = None) -> None: ...
    @property
    def database(self) -> Database: ...
    @property
    def changed_at(self) -> int: ...
    def observe(self) -> None: ...
    def changed(self) -> None: ...
    def changing(self) -> AbstractContextManager[None]: ...

class QueryCall:
    def __init__(self, memo: Any) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def args(self) -> tuple[Any, ...]: ...
    @property
    def kwargs(self) -> Mapping[str, Any]: ...
    def __hash__(self) -> int: ...
    def __eq__(self, other: object) -> bool: ...

class CycleContext:
    db: Database
    calls: tuple[QueryCall, ...]
    active: bool
    def __init__(self, db: Database, root: Any, cycle: CycleError, frame: Any) -> None: ...
    def evaluate(self, assumptions: Mapping[QueryCall, object]) -> Any: ...

class Database:
    name: str | None
    def __init__(self, *, name: str | None = None) -> None: ...
    @property
    def revision(self) -> int: ...
    @overload
    def input[V, R](self, value: V, *, adapter: ValueAdapter[V, R]) -> Input[R, V]: ...
    @overload
    def input[T: _Scalar](self, value: T, *, adapter: None = None) -> Input[T, T]: ...
    @overload
    def input[T: _Scalar](
        self, value: list[T], *, adapter: None = None
    ) -> Input[Sequence[T], list[T]]: ...
    @overload
    def input[K: _Scalar, V: _Scalar](
        self, value: dict[K, V], *, adapter: None = None
    ) -> Input[Mapping[K, V], dict[K, V]]: ...
    @overload
    def input[T: _Scalar](
        self, value: set[T], *, adapter: None = None
    ) -> Input[Set[T], set[T]]: ...
    @overload
    def input[T: _Scalar](
        self, value: frozenset[T], *, adapter: None = None
    ) -> Input[Set[T], frozenset[T]]: ...
    @overload
    def input[T: _Scalar](
        self, value: tuple[T, ...], *, adapter: None = None
    ) -> Input[Sequence[T], tuple[T, ...]]: ...
    @overload
    def input(
        self, value: bytearray, *, adapter: None = None
    ) -> Input[Sequence[int], bytearray]: ...
    @overload
    def input[T](
        self, value: list[T], *, adapter: None = None
    ) -> Input[Sequence[object], list[T]]: ...
    @overload
    def input[K, V](
        self, value: dict[K, V], *, adapter: None = None
    ) -> Input[Mapping[object, object], dict[K, V]]: ...
    @overload
    def input[T](self, value: set[T], *, adapter: None = None) -> Input[Set[object], set[T]]: ...
    @overload
    def input[T](
        self, value: frozenset[T], *, adapter: None = None
    ) -> Input[Set[object], frozenset[T]]: ...
    @overload
    def input[T](
        self, value: tuple[T, ...], *, adapter: None = None
    ) -> Input[Sequence[object], tuple[T, ...]]: ...
    def dependency(self, *, name: str | None = None) -> DependencyToken: ...
    def bind[**P, R](self, query: Tracked[P, R]) -> Callable[P, R]: ...
    def write(self) -> AbstractContextManager[Database]: ...
    def register_adapter[V, R](self, value_type: type[V], adapter: ValueAdapter[V, R]) -> None: ...
    def register_key[V](self, value_type: type[V], key: Callable[[V], object]) -> None: ...
    def cache_info(self) -> CacheInfo: ...
    def clear_cache(self) -> int: ...
    def prune(self, *, max_entries: int) -> int: ...
    def dependencies[**P, R](
        self, query: Tracked[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> tuple[QueryCall | Input[Any, Any] | DependencyToken, ...]: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: _ExitType, exc: _ExitValue, tb: _ExitTrace) -> None: ...

class Tracked[**P, R]:
    __name__: str
    __qualname__: str
    __wrapped__: Callable[P, object]
    @classmethod
    def __class_getitem__(cls, parameters: Any) -> Any: ...
    def __init__(
        self,
        function: Callable[P, R],
        *,
        equivalent: Callable[[R, R], bool] | None = None,
        result_adapter: ValueAdapter[Any, R] | None = None,
        solver: Callable[[CycleContext], R] | None = None,
    ) -> None: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    @overload
    def __get__(self, instance: None, owner: object = None) -> Self: ...
    @overload
    def __get__[Instance, **Q](
        self: Tracked[Concatenate[Instance, Q], R], instance: Instance, owner: object = None
    ) -> Callable[Q, R]: ...

class _Decorator:
    @overload
    def __call__[**P, T: _Scalar](self, fn: Callable[P, list[T]]) -> Tracked[P, Sequence[T]]: ...
    @overload
    def __call__[**P, K: _Scalar, V: _Scalar](
        self, fn: Callable[P, dict[K, V]]
    ) -> Tracked[P, Mapping[K, V]]: ...
    @overload
    def __call__[**P, T: _Scalar](
        self, fn: Callable[P, set[T] | frozenset[T]]
    ) -> Tracked[P, Set[T]]: ...
    @overload
    def __call__[**P, T: _Scalar](
        self, fn: Callable[P, tuple[T, ...]]
    ) -> Tracked[P, Sequence[T]]: ...
    @overload
    def __call__[**P](self, fn: Callable[P, bytearray]) -> Tracked[P, Sequence[int]]: ...
    @overload
    def __call__[**P, T](
        self, fn: Callable[P, list[T] | tuple[T, ...]]
    ) -> Tracked[P, Sequence[object]]: ...
    @overload
    def __call__[**P, K, V](
        self, fn: Callable[P, dict[K, V]]
    ) -> Tracked[P, Mapping[object, object]]: ...
    @overload
    def __call__[**P, T](
        self, fn: Callable[P, set[T] | frozenset[T]]
    ) -> Tracked[P, Set[object]]: ...
    @overload
    def __call__[**P, R](self, fn: Callable[P, R]) -> Tracked[P, R]: ...

@overload
def tracked[**P, V, R](
    function: Callable[P, V],
    *,
    equivalent: Callable[[R, R], bool] | None = None,
    result_adapter: ValueAdapter[V, R],
    solver: Callable[[CycleContext], V] | None = None,
) -> Tracked[P, R]: ...
@overload
def tracked[**P, T: _Scalar](
    function: Callable[P, list[T]],
    *,
    equivalent: Callable[[Sequence[T], Sequence[T]], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], Any] | None = None,
) -> Tracked[P, Sequence[T]]: ...
@overload
def tracked[**P, K: _Scalar, V: _Scalar](
    function: Callable[P, dict[K, V]],
    *,
    equivalent: Callable[[Mapping[K, V], Mapping[K, V]], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], Any] | None = None,
) -> Tracked[P, Mapping[K, V]]: ...
@overload
def tracked[**P, T: _Scalar](
    function: Callable[P, set[T] | frozenset[T]],
    *,
    equivalent: Callable[[Set[T], Set[T]], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], Any] | None = None,
) -> Tracked[P, Set[T]]: ...
@overload
def tracked[**P, T: _Scalar](
    function: Callable[P, tuple[T, ...]],
    *,
    equivalent: Callable[[Sequence[T], Sequence[T]], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], Any] | None = None,
) -> Tracked[P, Sequence[T]]: ...
@overload
def tracked[**P](
    function: Callable[P, bytearray],
    *,
    equivalent: Callable[[Sequence[int], Sequence[int]], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], Any] | None = None,
) -> Tracked[P, Sequence[int]]: ...
@overload
def tracked[**P, T](
    function: Callable[P, list[T] | tuple[T, ...]],
    *,
    equivalent: Callable[[Any, Any], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], Any] | None = None,
) -> Tracked[P, Sequence[object]]: ...
@overload
def tracked[**P, K, V](
    function: Callable[P, dict[K, V]],
    *,
    equivalent: Callable[[Any, Any], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], Any] | None = None,
) -> Tracked[P, Mapping[object, object]]: ...
@overload
def tracked[**P, T](
    function: Callable[P, set[T] | frozenset[T]],
    *,
    equivalent: Callable[[Any, Any], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], Any] | None = None,
) -> Tracked[P, Set[object]]: ...
@overload
def tracked[**P, R](
    function: Callable[P, R],
    *,
    equivalent: Callable[[R, R], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], R] | None = None,
) -> Tracked[P, R]: ...
@overload
def tracked[V, R](
    function: None = None,
    *,
    equivalent: Callable[[R, R], bool] | None = None,
    result_adapter: ValueAdapter[V, R],
    solver: Callable[[CycleContext], V] | None = None,
) -> _AdaptedDecorator[V, R]: ...
@overload
def tracked(
    function: None = None,
    *,
    equivalent: Callable[[Any, Any], bool] | None = None,
    result_adapter: None = None,
    solver: Callable[[CycleContext], Any] | None = None,
) -> _Decorator: ...

class _AdaptedDecorator[V, R]:
    def __call__[**P](self, fn: Callable[P, V]) -> Tracked[P, R]: ...
