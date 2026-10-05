"""Synchronous incremental engine with database-owned state and atomic publication."""

import functools
import inspect
import struct
import threading
import weakref
from collections import OrderedDict
from contextlib import contextmanager
from types import GenericAlias, MappingProxyType
from typing import Any, Callable, Dict, Iterator, NamedTuple, Optional, Tuple, cast

from ._adapters import ValueAdapter, builtin_adapter
from ._context import (
    CALLBACK,
    FRAME,
    SOLVING,
    callback_scope,
    check_callback,
    check_cancelled,
    current_frame,
    execution_identity,
)
from ._errors import (
    AdapterError,
    ClosedDatabaseError,
    CycleError,
    MutationError,
    OwnershipError,
    StaleViewError,
)
from ._views import _View

_MISSING = object()


class CacheInfo(NamedTuple):
    revision: int
    entries: int
    nodes: int
    hits: int
    validations: int
    executions: int
    evictions: int


class _Frame:
    def __init__(self, db: Any, memo: Any) -> None:
        self.db = db
        self.memo = memo
        self.owner = execution_identity()
        self.active = True
        self.dependencies: Dict[Any, int] = {}
        self.cacheable = True

    def observe(self, node: Any) -> None:
        previous = self.dependencies.setdefault(node, node.changed_at)
        if previous != node.changed_at:
            raise MutationError("A dependency changed during a query's read scope.")

    def absorb(self, other: "_Frame") -> None:
        for node in other.dependencies:
            self.observe(node)


class _Memo:
    def __init__(self, query: Any, args: Any, kwargs: Any) -> None:
        self.query = query
        self.args = args
        self.kwargs = dict(kwargs)
        self.value: Any = _MISSING
        self.adapter: Any = None
        self.dependencies: Tuple[Tuple[Any, int], ...] = ()
        self.verified_at = -1
        self.changed_at = 0
        self.cacheable = False
        self.busy = False


class _AliasChanges:
    """Conservative dependency for adapters without precise storage provenance."""

    changed_at = 0


class _Source:
    """Internal identity unaffected by a user's handle subclass equality/hash."""

    def __init__(self, handle: Any, stamp: int) -> None:
        self.handle = handle
        self.changed_at = stamp


class QueryCall:
    """A structured call identity for diagnostics and explicit cycle solvers."""

    def __init__(self, memo: _Memo) -> None:
        self._memo = memo

    @property
    def name(self) -> str:
        return str(self._memo.query.__qualname__)

    @property
    def args(self) -> Tuple[Any, ...]:
        return tuple(self._memo.args)

    @property
    def kwargs(self) -> Any:
        return MappingProxyType(self._memo.kwargs)

    def __hash__(self) -> int:
        return hash(self._memo)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, QueryCall) and self._memo is other._memo

    def __repr__(self) -> str:
        return "QueryCall({})".format(self.name)


class ReadGuard:
    """Lease used by adapters to protect an operation on borrowed storage.

    Hold this context for the entire native operation, not just a validity check.
    Nested values can be protected using protect(). Private attributes are not a
    security boundary against deliberate access to underlying Python objects.
    """

    def __init__(self, db: Any, source: Any = None) -> None:
        self._db = db
        self._source = source
        self._epoch = db._epoch
        self._stamp = source.changed_at if source is not None else 0
        self._locks: list[Any] = []

    def __enter__(self) -> "ReadGuard":
        scope = self._db._locked()
        scope.__enter__()
        try:
            if self._epoch != self._db._epoch:
                raise StaleViewError("This view predates a write. Read the input or query again.")
            self._db._observe(self._source)
        except BaseException:
            scope.__exit__(None, None, None)
            raise
        self._db._read_depth += 1
        self._locks.append(scope)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._db._read_depth -= 1
        self._locks.pop().__exit__(exc_type, exc, tb)

    def protect(self, value: Any) -> Any:
        with self:
            return self._db._read(value, self)


class Input:
    """A database-owned input. Use value for reading/replacement and edit for mutation."""

    def __class_getitem__(cls, parameters: Any) -> Any:
        return GenericAlias(cls, parameters)

    def __init__(self, database: "Database", value: Any, *, adapter: Any = None) -> None:
        self._db = database
        with database._locked():
            database._require_write()
            self._explicit_adapter = adapter
            self._adapter = database._adapter(value, adapter)
            self._value = value
            self._source = _Source(self, database._tick())
            self._editing = False

    @property
    def changed_at(self) -> int:
        check_callback()
        with self._db._locked():
            self._db._observe(self._source)
            return self._source.changed_at

    @property
    def database(self) -> "Database":
        return self._db

    @property
    def value(self) -> Any:
        check_callback()
        with self._db._locked():
            self._db._observe(self._source)
            if not self._adapter.stable:
                self._db._observe(self._db._alias_changes)
            return self._db._adapt_read(
                self._adapter, self._value, ReadGuard(self._db, self._source)
            )

    @value.setter
    def value(self, value: Any) -> None:
        with self._db.write():
            if self._editing:
                raise MutationError("Cannot replace an input while its editing scope is active.")
            adapter = self._db._adapter(value, self._explicit_adapter)
            self._db._touch(self._source)
            self._value = value
            self._adapter = adapter

    @contextmanager
    def edit(self) -> Iterator[Any]:
        with self._db.write():
            if self._editing:
                raise MutationError("The same input cannot have nested editing scopes.")
            if self._adapter.stable:
                raise AdapterError("Stable values require replacement using 'input.value = ...'.")
            self._editing = True
            self._db._touch(self._source)
            self._db._touch(self._db._alias_changes)
            try:
                with self._adapter.edit(self._value) as writable:
                    yield writable
            finally:
                self._editing = False

    def __repr__(self) -> str:
        return "Input(database={!r})".format(self._db.name)


class DependencyToken:
    """Observe and report changes to state managed outside the database."""

    def __init__(self, database: "Database", *, name: Optional[str] = None) -> None:
        self._db = database
        self.name = name
        with database._locked():
            database._require_write()
            self._source = _Source(self, database._tick())

    @property
    def changed_at(self) -> int:
        check_callback()
        with self._db._locked():
            self._db._observe(self._source)
            return self._source.changed_at

    @property
    def database(self) -> "Database":
        return self._db

    def observe(self) -> None:
        check_callback()
        with self._db._locked():
            self._db._observe(self._source)

    def changed(self) -> None:
        with self._db.write():
            self._db._touch(self._source)

    @contextmanager
    def changing(self) -> Iterator[None]:
        """Coordinate external writes with readers, including exceptional exit."""
        with self._db.write():
            self._db._touch(self._source)
            yield


class Tracked:
    """Reusable query definition; each database owns its own memo entries."""

    def __class_getitem__(cls, parameters: Any) -> Any:
        return GenericAlias(cls, parameters)

    def __init__(
        self,
        function: Callable[..., Any],
        *,
        equivalent: Any = None,
        result_adapter: Any = None,
        solver: Any = None,
    ) -> None:
        if inspect.iscoroutinefunction(function) or inspect.isgeneratorfunction(function):
            raise TypeError("Tracked queries must be synchronous, eager functions.")
        self._function = function
        # A wrapper can observe positional/keyword shape even when __wrapped__
        # advertises another function's signature. Key the callable we execute.
        self._signature = inspect.signature(function, follow_wrapped=False)
        self._equivalent = equivalent
        self._result_adapter = result_adapter
        self._solver = solver
        functools.update_wrapper(self, function, updated=())

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._invoke(None, args, kwargs)

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        if instance is None:
            return self
        return functools.partial(self, instance)

    def _invoke(self, bound_db: Any, args: Any, kwargs: Any) -> Any:
        check_callback()
        check_cancelled()
        frame = current_frame()
        db = bound_db
        if frame is not None:
            if db is not None and db is not frame.db:
                raise OwnershipError("Nested queries must use their parent's database.")
            db = frame.db
        bound = self._signature.bind(*args, **kwargs)
        bound.apply_defaults()
        for name, value in bound.arguments.items():
            parameter = self._signature.parameters[name]
            values = value.values() if parameter.kind is inspect.Parameter.VAR_KEYWORD else (value,)
            for item in values:
                for owner in _owners(item):
                    if db is not None and db is not owner:
                        raise OwnershipError("Query arguments belong to different databases.")
                    db = owner
        if db is None:
            raise OwnershipError("No database found. Bind this query once with 'db.bind(query)'.")
        with db._locked():
            memo = db._memo(self, bound, args, kwargs)
            solving = SOLVING.get()
            if solving is not None and solving.active and solving.db is db:
                return solving._call(memo)
            try:
                db._ensure(memo)
            except BaseException:
                if frame is not None:
                    frame.cacheable = False
                raise
            if frame is not None:
                if memo.cacheable:
                    frame.observe(memo)
                else:
                    frame.cacheable = False
                    for node, _stamp in memo.dependencies:
                        frame.observe(node)
            return db._read_memo(memo)


def tracked(
    function: Any = None, *, equivalent: Any = None, result_adapter: Any = None, solver: Any = None
) -> Any:
    """Decorate a synchronous function with database-local incremental memoization."""

    def decorate(fn: Callable[..., Any]) -> Tracked:
        return Tracked(fn, equivalent=equivalent, result_adapter=result_adapter, solver=solver)

    return decorate if function is None else decorate(function)


def _owners(value: Any) -> Iterator[Any]:
    if isinstance(value, (Input, DependencyToken)):
        yield value.database
    elif type(value) in (tuple, frozenset):
        for item in value:
            yield from _owners(item)
    else:
        owner = getattr(value, "__revlet_database__", None)
        if owner is not None:
            if not isinstance(owner, Database):
                raise OwnershipError("__revlet_database__ must be a Database instance.")
            yield owner


class Database:
    """An isolated execution domain with coordinated synchronous reads and writes."""

    def __init__(self, *, name: Optional[str] = None) -> None:
        self.name = name
        self._lock = threading.RLock()
        self._lock_owner: Any = None
        self._lock_depth = 0
        self._closed = False
        self._revision = 0
        self._clock = 0
        self._epoch = 0
        self._write_depth = 0
        self._read_depth = 0
        self._pending: set[Any] = set()
        self._alias_changes = _AliasChanges()
        self._stack: list[_Memo] = []
        self._nodes: Any = weakref.WeakValueDictionary()
        self._write_nodes: Any = weakref.WeakValueDictionary()
        self._cache: Any = OrderedDict()
        self._adapters: Dict[type, ValueAdapter] = {}
        self._key_adapters: Dict[type, Callable[..., Any]] = {}
        self._hits = self._validations = self._executions = self._evictions = 0

    @property
    def revision(self) -> int:
        with self._locked():
            return self._revision

    @contextmanager
    def _locked(self) -> Iterator[None]:
        check_cancelled()
        frame = current_frame()
        if frame is not None and frame.db is not self:
            # Reject before acquiring a foreign lock: two invalid cross-database
            # reads must not turn a useful ownership error into a deadlock.
            raise OwnershipError("Queries cannot enter another database's execution scope.")
        while not self._lock.acquire(timeout=0.05):
            check_cancelled()
        try:
            owner = execution_identity()
            if self._lock_depth and owner != self._lock_owner:
                raise MutationError("A synchronous database scope cannot be shared across tasks.")
            if self._closed:
                raise ClosedDatabaseError("This database is closed.")
            self._lock_owner = owner
            self._lock_depth += 1
            try:
                check_cancelled()
                yield
            finally:
                self._lock_depth -= 1
                if not self._lock_depth:
                    self._lock_owner = None
        finally:
            self._lock.release()

    def _tick(self) -> int:
        self._clock += 1
        return self._clock

    def _require_write(self) -> None:
        if self._read_depth or current_frame() is not None or CALLBACK.get() is not None:
            raise MutationError(
                "Queries, active read guards, and adapter callbacks cannot initiate managed writes."
            )

    def _observe(self, source: Any) -> None:
        frame = current_frame()
        if frame is not None:
            if frame.db is not self:
                raise OwnershipError("Queries cannot read inputs or views from another database.")
            if source is not None:
                if CALLBACK.get() != "Value adapters":
                    check_callback()
                frame.observe(source)

    @contextmanager
    def write(self) -> Iterator["Database"]:
        with self._locked():
            self._require_write()
            self._write_depth += 1
            # Entering a write invalidates borrowed views before any raw mutation.
            self._epoch += 1
            try:
                yield self
            finally:
                self._write_depth -= 1
                self._epoch += 1
                if not self._write_depth and self._pending:
                    self._revision += 1
                    for source in self._pending:
                        source.changed_at = self._tick()
                    self._pending.clear()

    def _touch(self, source: Any) -> None:
        self._pending.add(source)

    def input(self, value: Any, *, adapter: Any = None) -> Input:
        return Input(self, value, adapter=adapter)

    def dependency(self, *, name: Optional[str] = None) -> DependencyToken:
        return DependencyToken(self, name=name)

    def bind(self, query: Tracked) -> Callable[..., Any]:
        if not isinstance(query, Tracked):
            raise TypeError("Database.bind expects a @tracked query definition.")

        @functools.wraps(query)
        def bound(*args: Any, **kwargs: Any) -> Any:
            return query._invoke(self, args, kwargs)

        return bound

    def register_adapter(self, value_type: type, adapter: ValueAdapter) -> None:
        with self._locked():
            self._require_write()
            if value_type in self._adapters:
                raise AdapterError("An adapter is already registered for this exact type.")
            if builtin_adapter_for_type(value_type):
                raise AdapterError("Built-in adapters cannot be replaced; use an explicit adapter.")
            self._adapters[value_type] = adapter

    def register_key(self, value_type: type, key: Callable[..., Any]) -> None:
        with self._locked():
            self._require_write()
            if value_type in self._key_adapters:
                raise AdapterError("A key adapter is already registered for this exact type.")
            self._key_adapters[value_type] = key

    def _adapter(self, value: Any, explicit: Any = None) -> ValueAdapter:
        adapter = explicit
        if adapter is None:
            adapter = self._adapters.get(type(value)) or builtin_adapter(value)
        if not isinstance(adapter, ValueAdapter):
            raise AdapterError(
                "No protected value adapter for {}. Supply a ValueAdapter explicitly.".format(
                    type(value).__qualname__
                )
            )
        return adapter

    def _read(self, value: Any, guard: ReadGuard) -> Any:
        if isinstance(value, _View):
            old = value._guard
            if old._db is not self:
                raise OwnershipError("A result contains a view from another database.")
            if old._epoch != self._epoch:
                source = old._source
                if source is None:
                    raise StaleViewError("An expired temporary view cannot be published or reused.")
                if isinstance(source, _Memo):
                    self._ensure(source)
                if source.changed_at != old._stamp:
                    raise StaleViewError("A result contains a borrowed view of changed data.")
            self._observe(old._source)
            value = value._raw
        return self._adapt_read(self._adapter(value), value, guard)

    def _adapt_read(self, adapter: ValueAdapter, value: Any, guard: ReadGuard) -> Any:
        with callback_scope("Value adapters"):
            return adapter.read(value, guard)

    def _read_memo(self, memo: _Memo) -> Any:
        return self._adapt_read(
            memo.adapter, memo.value, ReadGuard(self, memo if memo.cacheable else None)
        )

    def _key(self, value: Any, adapting: bool = False) -> Any:
        kind = type(value)
        if isinstance(value, (Input, DependencyToken)):
            if value.database is not self:
                raise OwnershipError("A query key contains a handle from another database.")
            return kind, id(value)
        if kind in (type(None), bool, int, str, bytes):
            return kind, value
        if kind is float:
            return kind, struct.pack("!d", value)
        if kind is complex:
            return kind, struct.pack("!dd", value.real, value.imag)
        if kind is range:
            return kind, value.start, value.stop, value.step
        if kind is tuple:
            return kind, tuple(self._key(item, adapting) for item in value)
        if kind is frozenset:
            return kind, frozenset(self._key(item, adapting) for item in value)
        adapter = self._key_adapters.get(kind)
        if adapter is not None and not adapting:
            with callback_scope("Key adapters"):
                adapted = adapter(value)
            return kind, self._key(adapted, True)
        raise AdapterError(
            "No stable key for {}. Use a managed input or register a key adapter "
            "returning immutable built-in values.".format(kind.__qualname__)
        )

    def _memo(self, query: Tracked, bound: Any, args: Any, kwargs: Any) -> _Memo:
        parts = []
        for name, value in bound.arguments.items():
            parameter = query._signature.parameters[name]
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                part = tuple((k, self._key(v)) for k, v in value.items())
            else:
                part = self._key(value)
            parts.append((name, part))
        key = id(query), tuple(parts)
        nodes = self._write_nodes if self._write_depth else self._nodes
        memo = nodes.get(key)
        if memo is None:
            memo = _Memo(query, args, kwargs)
            nodes[key] = memo
        return cast(_Memo, memo)

    def _ensure(self, memo: _Memo) -> None:
        check_cancelled()
        if memo.busy:
            index = self._stack.index(memo)
            raise CycleError([QueryCall(node) for node in self._stack[index:] + [memo]])
        if not self._write_depth and memo.cacheable and memo.verified_at == self._revision:
            self._hits += 1
            self._cache.move_to_end(memo)
            return
        memo.busy = True
        self._stack.append(memo)
        try:
            if not self._write_depth and memo.cacheable and memo.value is not _MISSING:
                self._validations += 1
                valid = True
                for dependency, stamp in memo.dependencies:
                    check_cancelled()
                    if isinstance(dependency, _Memo):
                        self._ensure(dependency)
                    if dependency.changed_at != stamp or (
                        isinstance(dependency, _Memo) and not dependency.cacheable
                    ):
                        valid = False
                        break
                if valid:
                    memo.verified_at = self._revision
                    self._cache.move_to_end(memo)
                    return
            self._execute(memo)
        finally:
            self._stack.pop()
            memo.busy = False

    def _execute(self, memo: _Memo) -> None:
        parent = current_frame()
        frame = _Frame(self, memo)
        token = FRAME.set(frame)
        self._executions += 1
        try:
            try:
                value = memo.query._function(*memo.args, **memo.kwargs)
            except CycleError as cycle:
                if memo.query._solver is None:
                    raise
                frame.cacheable = True
                session = CycleContext(self, memo, cycle, frame)
                try:
                    value = memo.query._solver(session)
                finally:
                    session.active = False
            if inspect.isawaitable(value):
                if inspect.iscoroutine(value):
                    value.close()
                raise TypeError(
                    "A tracked query returned an awaitable; eager results are required."
                )
            if isinstance(value, _View):
                # Observe a directly returned borrow before detaching its old read lease.
                with value._guard:
                    value = value._raw
            adapter = self._adapter(value, memo.query._result_adapter)
            if not adapter.stable:
                frame.observe(self._alias_changes)
            # Validate that the adapter can publish a protected interface before committing.
            new_read = self._adapt_read(adapter, value, ReadGuard(self))
            same = False
            if (
                not self._write_depth
                and memo.value is not _MISSING
                and memo.adapter is adapter
                and adapter.stable
            ):
                comparator = memo.query._equivalent or adapter.equivalent
                old_read = self._adapt_read(adapter, memo.value, ReadGuard(self))
                with callback_scope("Result comparators"):
                    equal = comparator(old_read, new_read)
                if type(equal) is not bool:
                    raise AdapterError(
                        "Result equivalence must return bool, not an array or proxy."
                    )
                same = equal
            check_cancelled()
            cacheable = frame.cacheable and not self._write_depth
            if not same:
                memo.value = value
                memo.adapter = adapter
                memo.changed_at = self._tick()
            memo.dependencies = tuple(frame.dependencies.items())
            memo.cacheable = cacheable
            memo.verified_at = self._revision if cacheable else -1
            if cacheable:
                self._cache[memo] = None
                self._cache.move_to_end(memo)
            else:
                self._cache.pop(memo, None)
        except BaseException:
            # Retain an old stable comparison anchor, but never a valid partial memo.
            memo.cacheable = False
            memo.verified_at = -1
            self._cache.pop(memo, None)
            if parent is not None:
                parent.absorb(frame)
                parent.cacheable = False
            raise
        finally:
            frame.active = False
            FRAME.reset(token)

    def cache_info(self) -> CacheInfo:
        with self._locked():
            return CacheInfo(
                self._revision,
                len(self._cache),
                len(self._nodes),
                self._hits,
                self._validations,
                self._executions,
                self._evictions,
            )

    def _evict(self, memo: _Memo) -> None:
        self._cache.pop(memo, None)
        memo.value = _MISSING
        memo.adapter = None
        memo.dependencies = ()
        memo.cacheable = False
        memo.verified_at = -1
        self._evictions += 1

    def clear_cache(self) -> int:
        with self._locked():
            self._require_write()
            count = len(self._cache)
            for memo in list(self._cache):
                self._evict(memo)
            self._epoch += 1
            return count

    def prune(self, *, max_entries: int) -> int:
        """Explicitly evict least recently used values to the caller's entry budget."""
        if type(max_entries) is not int or max_entries < 0:
            raise ValueError("max_entries must be a non-negative integer.")
        with self._locked():
            self._require_write()
            count = 0
            while len(self._cache) > max_entries:
                memo = next(iter(self._cache))
                self._evict(memo)
                count += 1
            if count:
                self._epoch += 1
            return count

    def dependencies(self, query: Tracked, *args: Any, **kwargs: Any) -> Tuple[Any, ...]:
        with self._locked():
            bound = query._signature.bind(*args, **kwargs)
            bound.apply_defaults()
            memo = self._memo(query, bound, args, kwargs)
            return tuple(
                QueryCall(node) if isinstance(node, _Memo) else node.handle
                for node, _stamp in memo.dependencies
                if not isinstance(node, _AliasChanges)
            )

    def close(self) -> None:
        # Idempotence must also hold outside a cancellation scope.
        self._require_write()
        with self._lock:
            if self._closed:
                return
            if self._write_depth or self._lock_depth:
                raise MutationError("Close the database after its active scopes have finished.")
            self._cache.clear()
            self._nodes.clear()
            self._write_nodes.clear()
            self._adapters.clear()
            self._key_adapters.clear()
            self._closed = True
            self._epoch += 1

    def __enter__(self) -> "Database":
        with self._locked():
            return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


def builtin_adapter_for_type(value_type: type) -> bool:
    from ._adapters import SCALARS

    return value_type in SCALARS + (list, tuple, dict, set, frozenset, bytearray)


class CycleContext:
    """Isolated evaluation for a caller-provided cycle solver.

    evaluate(assumptions) evaluates the original query with explicit provisional
    call values. The solver chooses iteration and convergence, then returns its
    final result. Only that final result may become an ordinary memo.
    """

    def __init__(self, db: Database, root: _Memo, cycle: CycleError, frame: _Frame) -> None:
        self.db = db
        self._root = root
        self.calls = cycle.calls
        self._frame = frame
        self.active = True
        self._assumptions: Dict[_Memo, Any] = {}
        self._evaluating: list[_Memo] = []

    def evaluate(self, assumptions: Any) -> Any:
        if not self.active or current_frame() is not self._frame:
            raise MutationError("A cycle context is only usable inside its solver callback.")
        self._assumptions = {}
        for call, value in assumptions.items():
            if not isinstance(call, QueryCall) or call not in self.calls:
                raise ValueError("Cycle assumptions must refer to calls in this cycle.")
            self._assumptions[call._memo] = value
        token = SOLVING.set(self)
        try:
            return self._evaluate(self._root)
        finally:
            SOLVING.reset(token)
            self._assumptions = {}

    def _call(self, memo: _Memo) -> Any:
        if memo in self._assumptions:
            return self.db._read(self._assumptions[memo], ReadGuard(self.db))
        return self._evaluate(memo)

    def _evaluate(self, memo: _Memo) -> Any:
        check_cancelled()
        if memo in self._evaluating:
            index = self._evaluating.index(memo)
            raise CycleError([QueryCall(n) for n in self._evaluating[index:] + [memo]])
        self._evaluating.append(memo)
        self.db._executions += 1
        # All provisional reads go directly into the solver's frame. No ordinary
        # memo can depend on, or retain, an intermediate iteration result.
        try:
            value = memo.query._function(*memo.args, **memo.kwargs)
            if isinstance(value, _View):
                with value._guard:
                    value = value._raw
            adapter = self.db._adapter(value, memo.query._result_adapter)
            return self.db._adapt_read(adapter, value, ReadGuard(self.db))
        finally:
            self._evaluating.pop()
