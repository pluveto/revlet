"""Explicit value capabilities, without implicit copying or serialization."""

import copy
import struct
from contextlib import contextmanager
from types import GenericAlias
from typing import Any, Iterator

from ._errors import AdapterError
from ._views import _FrozenSetView, _MappingView, _SequenceView, _SetView, _TupleView, _View

SCALARS = (type(None), bool, int, float, complex, str, bytes, range)


class ValueAdapter:
    """Override read/edit/equivalent for a value type.

    stable means a published value remains a valid comparison anchor across
    managed writes. Setting it to True is a correctness promise by the adapter.
    """

    stable = False

    def __class_getitem__(cls, parameters: Any) -> Any:
        return GenericAlias(cls, parameters)

    def read(self, value: Any, guard: Any) -> Any:
        raise AdapterError("Implement ValueAdapter.read(value, guard) for this type.")

    def edit(self, value: Any) -> Any:
        raise AdapterError("This adapter does not provide writable access.")

    def equivalent(self, old: Any, new: Any) -> bool:
        return False


class _ScalarAdapter(ValueAdapter):
    stable = True

    def read(self, value: Any, guard: Any) -> Any:
        return value

    def equivalent(self, old: Any, new: Any) -> bool:
        if type(old) is not type(new):
            return False
        if type(old) is float:
            # Signed zero and NaN payloads can be observed by downstream code.
            return struct.pack("!d", old) == struct.pack("!d", new)
        if type(old) is complex:
            return struct.pack("!dd", old.real, old.imag) == struct.pack("!dd", new.real, new.imag)
        if type(old) is range:
            return (old.start, old.stop, old.step) == (new.start, new.stop, new.step)
        return bool(old == new)


class _ContainerAdapter(ValueAdapter):
    def read(self, value: Any, guard: Any) -> Any:
        if type(value) in (list, bytearray):
            return _SequenceView(value, guard)
        if type(value) is tuple:
            return _TupleView(value, guard)
        if type(value) is dict:
            return _MappingView(value, guard)
        if type(value) is frozenset:
            return _FrozenSetView(value, guard)
        return _SetView(value, guard)

    @contextmanager
    def edit(self, value: Any) -> Iterator[Any]:
        if type(value) in (tuple, frozenset):
            raise AdapterError("Replace this immutable container using 'input.value = ...'.")
        yield value


SCALAR_ADAPTER = _ScalarAdapter()
CONTAINER_ADAPTER = _ContainerAdapter()


def builtin_adapter(value: Any) -> Any:
    if type(value) in SCALARS:
        return SCALAR_ADAPTER
    if type(value) in (list, tuple, dict, set, frozenset, bytearray):
        return CONTAINER_ADAPTER
    return None


def copy_value(value: Any, memo: Any = None) -> Any:
    """Make an explicit deep copy, including guarded containers and cycles.

    Custom read interfaces use their own deepcopy implementation. Computational
    adapters should expose an explicit native copying operation when preferable.
    """
    if memo is None:
        memo = {}
    if isinstance(value, _View):
        with value._guard:
            raw = value._raw
            identity = id(raw)
            if identity in memo:
                return memo[identity]
            if type(raw) is dict:
                result: dict[Any, Any] = {}
                memo[identity] = result
                for key in raw:
                    result[copy_value(value._guard.protect(key), memo)] = copy_value(
                        value._guard.protect(raw[key]), memo
                    )
                return result
            if type(raw) is tuple:
                items = [copy_value(value._guard.protect(item), memo) for item in raw]
                if identity in memo:
                    return memo[identity]
                result_tuple = tuple(items)
                memo[identity] = result_tuple
                return result_tuple
            if type(raw) is list:
                result_list: list[Any] = []
                memo[identity] = result_list
                for item in raw:
                    result_list.append(copy_value(value._guard.protect(item), memo))
                return result_list
            if type(raw) is bytearray:
                result_bytes = bytearray(raw)
                memo[identity] = result_bytes
                return result_bytes
            if type(raw) is frozenset:
                result_frozen = frozenset(
                    copy_value(value._guard.protect(item), memo) for item in raw
                )
                memo[identity] = result_frozen
                return result_frozen
            result_set: set[Any] = set()
            memo[identity] = result_set
            for item in raw:
                result_set.add(copy_value(value._guard.protect(item), memo))
            return result_set
    return copy.deepcopy(value, memo)
