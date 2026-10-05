"""Lazy, guarded views for built-in containers."""

from collections.abc import Mapping, Sequence, Set
from typing import Any, Iterable, Iterator, NoReturn

from ._errors import ReadOnlyError


def _readonly(*args: Any, **kwargs: Any) -> NoReturn:
    raise ReadOnlyError(
        "This value is read-only. Use 'with input.edit()' to edit an input, "
        "or explicitly make an independent copy of a query result."
    )


class _View:
    __slots__ = ("_guard", "_raw")

    def __init__(self, raw: Any, guard: Any) -> None:
        self._raw = raw
        self._guard = guard

    def __repr__(self) -> str:
        with self._guard:
            return "{}({!r})".format(type(self).__name__, self._raw)

    def __copy__(self) -> Any:
        return self

    def __deepcopy__(self, memo: Any) -> Any:
        # Public iteration preserves adapter protections; raw storage is never returned.
        from ._adapters import copy_value

        return copy_value(self, memo)


class _SequenceView(_View, Sequence[Any]):
    __slots__ = ()

    def __len__(self) -> int:
        with self._guard:
            return len(self._raw)

    def __getitem__(self, index: Any) -> Any:
        with self._guard:
            return self._guard.protect(self._raw[index])

    def __iter__(self) -> Iterator[Any]:
        index = 0
        while True:
            with self._guard:
                if index >= len(self._raw):
                    return
                value = self._guard.protect(self._raw[index])
            yield value
            index += 1

    def __eq__(self, other: Any) -> Any:
        if not isinstance(other, Sequence):
            return NotImplemented
        return len(self) == len(other) and all(a == b for a, b in zip(self, other))

    __hash__: Any = None
    __setitem__ = __delitem__ = __iadd__ = __imul__ = _readonly
    append = extend = insert = pop = remove = clear = reverse = sort = _readonly


class _MappingView(_View, Mapping[Any, Any]):
    __slots__ = ()

    def __len__(self) -> int:
        with self._guard:
            return len(self._raw)

    def __getitem__(self, key: Any) -> Any:
        with self._guard:
            return self._guard.protect(self._raw[key])

    def __iter__(self) -> Iterator[Any]:
        with self._guard:
            iterator = iter(self._raw)
        while True:
            with self._guard:
                try:
                    key = next(iterator)
                except StopIteration:
                    return
                value = self._guard.protect(key)
            yield value

    __setitem__ = __delitem__ = __ior__ = _readonly
    clear = pop = popitem = setdefault = update = _readonly


class _TupleView(_SequenceView):
    __slots__ = ()

    def __eq__(self, other: Any) -> Any:
        if type(other) is tuple or isinstance(other, _TupleView):
            return super().__eq__(other)
        return NotImplemented

    def __hash__(self) -> int:
        with self._guard:
            return hash(self._raw)


class _SetView(_View, Set[Any]):
    __slots__ = ()

    @classmethod
    def _from_iterable(cls, values: Iterable[Any]) -> Any:
        return frozenset(values)

    def __len__(self) -> int:
        with self._guard:
            return len(self._raw)

    def __contains__(self, value: Any) -> bool:
        with self._guard:
            return value in self._raw

    def __iter__(self) -> Iterator[Any]:
        with self._guard:
            iterator = iter(self._raw)
        while True:
            with self._guard:
                try:
                    item = next(iterator)
                except StopIteration:
                    return
                value = self._guard.protect(item)
            yield value

    __iand__ = __ior__ = __isub__ = __ixor__ = _readonly
    add = clear = discard = pop = remove = update = _readonly
    difference_update = intersection_update = symmetric_difference_update = _readonly


class _FrozenSetView(_SetView):
    __slots__ = ()

    def __hash__(self) -> int:
        with self._guard:
            return hash(self._raw)
