"""Adapter read operations cannot silently acquire hidden dependencies or mutate inputs."""

import pytest

from revlet import AdapterError, Database, MutationError, ReadGuard, ValueAdapter, tracked


def test_adapter_cannot_mutate_managed_state_outside_query():
    db = Database()
    other = db.input(1)

    class Adapter(ValueAdapter):
        def read(self, value, guard):
            other.value = 2
            return value

    value = db.input([1], adapter=Adapter())
    with pytest.raises(MutationError):
        _ = value.value
    assert other.value == 1


def test_adapter_cannot_read_hidden_inputs():
    db = Database()
    other = db.input(1)

    class Adapter(ValueAdapter):
        def read(self, value, guard):
            return other.value

    value = db.input([1], adapter=Adapter())
    with pytest.raises(AdapterError):
        _ = value.value


def test_reentrant_write_cannot_interrupt_a_guarded_read_operation():
    db = Database()
    value = db.input(1)
    with ReadGuard(db):
        with pytest.raises(MutationError):
            value.value = 2
    assert value.value == 1
    value.value = 2
    assert value.value == 2


def test_native_style_operation_holds_its_read_guard():
    class Vector:
        def __init__(self, data):
            self.data = data

    class ReadVector:
        def __init__(self, value, guard):
            self.value = value
            self.guard = guard

        def total(self):
            with self.guard:
                return sum(self.value.data)

    class Adapter(ValueAdapter):
        def read(self, value, guard):
            with guard:
                return ReadVector(value, guard)

    db = Database()
    value = db.input(Vector([1, 2]), adapter=Adapter())

    @tracked
    def total(x):
        return x.value.total()

    assert total(value) == 3
