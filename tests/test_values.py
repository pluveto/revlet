"""Managed mutation, nested read protection, aliases, and view lifetimes."""

import copy

import pytest

from revlet import (
    AdapterError,
    Database,
    MutationError,
    ReadOnlyError,
    StaleViewError,
    copy_value,
    tracked,
)


def test_nested_reads_reject_mutation_and_copy_is_independent():
    db = Database()
    items = db.input([{"tags": ["a"]}])
    read = items.value
    with pytest.raises(ReadOnlyError):
        read.append({})
    with pytest.raises(ReadOnlyError):
        read[0]["tags"].append("b")
    with pytest.raises(ReadOnlyError):
        read[0]["tags"] = []
    writable = copy_value(read)
    writable[0]["tags"].append("b")
    assert list(items.value[0]["tags"]) == ["a"]
    assert copy.deepcopy(read) == [{"tags": ["a"]}]


def test_copy_preserves_cycles_and_shared_containers():
    db = Database()
    raw = []
    raw.append(raw)
    result = copy_value(db.input(raw).value)
    assert result[0] is result
    child = [1]
    result = copy_value(db.input({("key",): [child, child]}).value)
    assert result[("key",)][0] is result[("key",)][1]


def test_protected_mapping_keys_round_trip_through_iteration():
    db = Database()
    value = db.input({("key",): 1, frozenset({2}): 3}).value
    assert sorted(value[key] for key in value) == [1, 3]
    assert dict(value) == {("key",): 1, frozenset({2}): 3}


def test_edit_exit_registers_changes_even_on_failure():
    db = Database()
    items = db.input([1])

    @tracked
    def total(x):
        return sum(x.value)

    assert total(items) == 1
    before = db.revision
    with pytest.raises(ValueError, match="body"):
        with items.edit() as values:
            values.append(2)
            raise ValueError("body")
    assert db.revision == before + 1
    assert total(items) == 3


def test_queries_during_edit_see_current_data_without_publishing():
    db = Database()
    items = db.input([1])

    @tracked
    def total(x):
        return sum(x.value)

    assert total(items) == 1
    before = db.cache_info().entries
    with items.edit() as values:
        values.append(2)
        assert total(items) == 3
        values.append(3)
        assert total(items) == 6
        assert db.cache_info().entries == before
    assert total(items) == 6


def test_write_scope_groups_revisions_and_does_not_rollback():
    db = Database()
    left, right = db.input(1), db.input(2)

    @tracked
    def total(a, b):
        return a.value + b.value

    before = db.revision
    with pytest.raises(RuntimeError):
        with db.write():
            left.value = 10
            right.value = 20
            assert total(left, right) == 30
            raise RuntimeError()
    assert db.revision == before + 1
    assert total(left, right) == 30


def test_shared_input_storage_and_aliased_results_cannot_backdate():
    db = Database()
    storage = [1]
    left, right = db.input(storage), db.input(storage)

    @tracked(equivalent=lambda old, new: old == new)
    def alias(x):
        return x.value

    @tracked
    def total(x):
        return sum(alias(x))

    assert total(right) == 1
    with left.edit() as values:
        values.append(2)
    assert total(right) == 3


def test_nested_shared_storage_is_conservatively_invalidated():
    db = Database()
    shared = [1]
    one, two = db.input({"x": shared}), db.input([shared])

    @tracked
    def total(x):
        return sum(x.value[0])

    assert total(two) == 1
    with one.edit() as value:
        value["x"].append(2)
    assert total(two) == 3


def test_old_views_expire_and_cached_nested_views_are_rebased_safely():
    db = Database()
    items, unrelated = db.input([1]), db.input(1)
    calls = []

    @tracked
    def result(x):
        calls.append(1)
        return {"items": x.value}

    old = result(items)
    unrelated.value = 2
    with pytest.raises(StaleViewError):
        len(old)
    current = result(items)
    assert list(current["items"]) == [1]
    assert len(calls) == 1
    with items.edit() as values:
        values.append(2)
    assert list(result(items)["items"]) == [1, 2]


def test_nested_edit_same_input_and_replacement_are_rejected():
    items = Database().input([])
    with items.edit():
        with pytest.raises(MutationError):
            with items.edit():
                pass
        with pytest.raises(MutationError):
            items.value = []


def test_unsupported_mutable_value_requires_adapter():
    class Mutable:
        pass

    db = Database()
    with pytest.raises(AdapterError, match="ValueAdapter"):
        db.input(Mutable())
    nested = db.input([Mutable()])
    with pytest.raises(AdapterError):
        nested.value[0]


@pytest.mark.parametrize("raw", [[1], {"a": 1}, {1}, bytearray(b"a")])
def test_iteration_checks_the_view_after_writes(raw):
    db = Database()
    source = db.input(raw)
    iterator = iter(source.value)
    assert next(iterator) is not None
    db.input(1).value = 2
    with pytest.raises(StaleViewError):
        next(iterator)
