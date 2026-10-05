"""Explicit extension contracts and isolated cycle solving."""

from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from revlet import AdapterError, CycleError, Database, MutationError, ValueAdapter, tracked


def test_cycle_reports_structured_path_and_does_not_poison_cache():
    db = Database()
    source = db.input(True)

    @tracked
    def a(x):
        return b(x) if x.value else 42

    @tracked
    def b(x):
        return a(x)

    with pytest.raises(CycleError) as raised:
        a(source)
    calls = raised.value.calls
    assert calls[0] == calls[-1]
    assert calls[0].args == (source,)
    assert calls[0].name.endswith("a")
    assert calls[1].name.endswith("b")
    assert db.cache_info().entries == 0
    source.value = False
    assert a(source) == 42


def test_explicit_solver_publishes_only_final_result_and_tracks_iteration_reads():
    db = Database()
    limit = db.input(3)
    sessions = []
    iterations = []

    def solve(context):
        sessions.append(context)
        value = 0
        for _ in range(100):
            next_value = context.evaluate({context.calls[-1]: value})
            iterations.append(next_value)
            if next_value == value:
                return value
            value = next_value
        raise RuntimeError("The application solver did not converge.")

    @tracked(solver=solve)
    def fixed(x):
        return min(x.value, fixed(x) + 1)

    assert fixed(limit) == 3
    assert iterations == [1, 2, 3, 3]
    assert db.cache_info().entries == 1
    assert fixed(limit) == 3
    assert len(sessions) == 1
    limit.value = 5
    assert fixed(limit) == 5
    with pytest.raises(MutationError):
        sessions[-1].evaluate({})


def test_solver_keeps_dependencies_from_the_original_cycle_path():
    db = Database()
    enabled = db.input(True)

    @tracked(solver=lambda context: 10)
    def query(x):
        return query(x) if x.value else 20

    assert query(enabled) == 10
    enabled.value = False
    assert query(enabled) == 20


def test_failed_solver_does_not_publish_provisional_results():
    db = Database()

    def solve(context):
        assert context.evaluate({context.calls[-1]: 0}) == 1
        raise RuntimeError("No convergence")

    @tracked(solver=solve)
    def cycle():
        return cycle() + 1

    with pytest.raises(RuntimeError, match="No convergence"):
        db.bind(cycle)()
    assert db.cache_info().entries == 0


@dataclass(frozen=True)
class Point:
    x: int


class PointAdapter(ValueAdapter[Point, Point]):
    stable = True

    def read(self, value, guard):
        return value

    def equivalent(self, old, new):
        return old == new


def test_explicit_adapter_and_result_equivalence():
    db = Database()
    adapter = PointAdapter()
    point = db.input(Point(1), adapter=adapter)
    calls = []

    @tracked(result_adapter=adapter)
    def identity(x):
        return x.value

    @tracked
    def outer(x):
        calls.append(1)
        return identity(x).x

    assert outer(point) == 1
    point.value = Point(1)
    assert outer(point) == 1
    assert len(calls) == 1
    point.value = Point(2)
    assert outer(point) == 2


def test_adapter_edit_failure_still_registers_potential_mutation():
    class FailingAdapter(ValueAdapter):
        def read(self, value, guard):
            return guard.protect(value)

        @contextmanager
        def edit(self, value):
            value.append(2)
            raise RuntimeError("adapter failed before yielding")
            yield value

    db = Database()
    source = db.input([1], adapter=FailingAdapter())

    @tracked
    def total(x):
        return sum(x.value)

    assert total(source) == 1
    with pytest.raises(RuntimeError, match="before yielding"):
        with source.edit():
            pass
    assert total(source) == 3


def test_comparator_must_return_bool():
    db = Database()
    source = db.input(1)

    @tracked(equivalent=lambda a, b: 1)
    def identity(x):
        return x.value

    assert identity(source) == 1
    source.value = 2
    with pytest.raises(AdapterError, match="bool"):
        identity(source)
