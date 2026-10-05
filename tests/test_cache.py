"""Reclamation keeps dependency identity sound and releases unused payloads."""

import gc
import weakref

import pytest

from revlet import Database, ValueAdapter, tracked


def test_evicted_dependency_is_recomputed_before_reusing_parent():
    db = Database()
    source = db.input(1)

    @tracked
    def child(x):
        return x.value + 1

    @tracked
    def parent(x):
        return child(x) * 2

    assert parent(source) == 4
    assert db.prune(max_entries=1) == 1
    source.value = 2
    assert parent(source) == 6


def test_clear_releases_results_and_argument_handles():
    class Payload:
        pass

    class Adapter(ValueAdapter):
        stable = True

        def read(self, value, guard):
            return value

    db = Database()
    references = []

    @tracked(result_adapter=Adapter())
    def make(source):
        _ = source.value
        value = Payload()
        references.append(weakref.ref(value))
        return value

    source = db.input(1)
    handle = weakref.ref(source)
    make(source)
    del source
    assert references[0]() is not None
    assert handle() is not None
    assert db.clear_cache() == 1
    gc.collect()
    assert references[0]() is None
    assert handle() is None
    assert db.cache_info().nodes == 0


@pytest.mark.parametrize("budget", [-1, 1.0, True])
def test_prune_rejects_invalid_budgets(budget):
    with pytest.raises(ValueError):
        Database().prune(max_entries=budget)


def test_retained_guarded_result_does_not_turn_eviction_into_a_false_hit():
    db = Database()
    source = db.input(1)

    @tracked
    def query(x):
        return [x.value]

    old = query(source)
    assert db.clear_cache() == 1
    source.value = 2
    assert list(query(source)) == [2]
    assert old is not None
