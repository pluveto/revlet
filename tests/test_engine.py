"""Behavioral tests for validation, publication, and database isolation."""

import contextvars
import functools
import math
import random

import pytest

from revlet import (
    AdapterError,
    Database,
    Input,
    MutationError,
    OwnershipError,
    tracked,
)


def test_transitive_validation_and_early_cutoff():
    db = Database()
    source = db.input(1)
    calls = []

    @tracked
    def parity(x):
        calls.append("parity")
        return x.value % 2

    @tracked
    def outer(x):
        calls.append("outer")
        return parity(x) + 10

    assert outer(source) == outer(source) == 11
    source.value = 3
    assert outer(source) == 11
    assert calls == ["outer", "parity", "parity"]
    source.value = 4
    assert outer(source) == 10
    assert calls == ["outer", "parity", "parity", "parity", "outer"]


def test_dynamic_dependencies_replace_previous_branch():
    db = Database()
    switch, left, right = db.input(True), db.input(1), db.input(2)
    calls = []

    @tracked
    def choose():
        calls.append(1)
        return left.value if switch.value else right.value

    run = db.bind(choose)
    assert run() == 1
    switch.value = False
    assert run() == 2
    left.value = 99
    assert run() == 2
    assert len(calls) == 2
    assert db.dependencies(choose) == (switch, right)


def test_validation_stops_before_obsolete_failing_branch():
    db = Database()
    switch, value = db.input(True), db.input(1)

    @tracked
    def may_fail():
        return 10 // value.value

    @tracked
    def root():
        return may_fail() if switch.value else 42

    run = db.bind(root)
    assert run() == 10
    with db.write():
        switch.value = False
        value.value = 0
    assert run() == 42


def test_cutoff_retains_published_anchor_and_new_dependencies():
    db = Database()
    source, other, switch = db.input(10.0), db.input(10.06), db.input(True)

    @tracked(equivalent=lambda old, new: abs(old - new) < 0.1)
    def value():
        return source.value if switch.value else other.value

    run = db.bind(value)
    assert run() == 10.0
    switch.value = False
    assert run() == 10.0
    assert db.dependencies(value) == (switch, other)
    other.value = 10.12
    assert run() == 10.12


def test_database_ownership_and_binding():
    one, two = Database(), Database()
    a, b = one.input(1), two.input(2)

    @tracked
    def add(x, y=1):
        return x.value + y

    assert add(a) == 2
    assert add(b) == 3
    with pytest.raises(OwnershipError):
        one.bind(add)(b)

    @tracked
    def hidden_foreign_read(x):
        return x.value + b.value

    with pytest.raises(OwnershipError):
        hidden_foreign_read(a)

    @tracked
    def constant():
        return 1

    with pytest.raises(OwnershipError, match="bind"):
        constant()
    assert one.bind(constant)() == two.bind(constant)() == 1


def test_key_binding_types_signed_zero_and_keyword_order():
    db = Database()
    calls = []

    @tracked
    def show(x=1, **kw):
        calls.append(1)
        return repr((type(x).__name__, x, list(kw)))

    run = db.bind(show)
    assert run() == run(1) == run(x=1)
    assert len(calls) == 1
    assert run(True) != run(1)
    assert run(0.0) != run(-0.0)
    assert run(a=1, b=2) != run(b=2, a=1)
    with pytest.raises(AdapterError, match="stable key"):
        run([])


def test_decorated_function_keys_follow_its_actual_call_binding():
    def original(value=1):
        return value

    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        return len(kwargs)

    query = Database().bind(tracked(wrapper))
    assert query(1) == 0
    assert query(value=1) == 1


def test_key_adapter_and_bound_method():
    db = Database()

    class Model:
        __revlet_database__ = db

        def __init__(self, source):
            self.source = source

        @tracked
        def calculate(self, factor=2):
            return self.source.value * factor

    db.register_key(Model, lambda model: model.source)
    model = Model(db.input(3))
    assert model.calculate() == 6
    model.source.value = 4
    assert model.calculate(factor=3) == 12


def test_managed_handle_identity_does_not_use_user_equality_or_hashing():
    class EqualInputs(Input):
        __hash__ = None

        def __eq__(self, other):
            return True

    db = Database()
    one, two = EqualInputs(db, 1), EqualInputs(db, 2)

    @tracked
    def identity(x):
        return x.value

    @tracked
    def total():
        return one.value + two.value

    assert identity(one) == 1
    assert identity(two) == 2
    assert db.bind(total)() == 3
    two.value = 5
    assert db.bind(total)() == 6
    assert identity(one) == 1
    assert identity(two) == 5


def test_failed_child_caught_by_parent_does_not_create_stale_cache():
    db = Database()
    source = db.input(0)
    parent_calls = []

    @tracked
    def child():
        return 10 // source.value

    @tracked
    def parent():
        parent_calls.append(1)
        try:
            return child()
        except ZeroDivisionError:
            return -1

    run = db.bind(parent)
    assert run() == run() == -1
    assert len(parent_calls) == 2
    source.value = 2
    assert run() == run() == 5
    assert len(parent_calls) == 3


def test_comparator_failure_does_not_publish_or_corrupt_context():
    db = Database()
    source = db.input(1)

    def equivalent(a, b):
        raise LookupError("comparison failed")

    @tracked(equivalent=equivalent)
    def run(x):
        return x.value

    assert run(source) == 1
    source.value = 2
    with pytest.raises(LookupError, match="comparison failed"):
        run(source)
    source.value = 3
    db.clear_cache()
    assert run(source) == 3


def test_query_mutations_and_stateful_key_callbacks_are_rejected():
    db = Database()
    source = db.input(1)

    @tracked
    def bad(x):
        x.value = 2
        return 1

    with pytest.raises(MutationError):
        bad(source)
    assert source.value == 1

    class Key:
        pass

    db.register_key(Key, lambda key: source.value)

    @tracked
    def run(key):
        return 1

    with pytest.raises(AdapterError):
        db.bind(run)(Key())


def test_expired_copied_context_does_not_inherit_database():
    db = Database()
    contexts = []

    @tracked
    def capture():
        contexts.append(contextvars.copy_context())
        return 1

    @tracked
    def unbound():
        return 2

    assert db.bind(capture)() == 1
    with pytest.raises(OwnershipError):
        contexts[0].run(unbound)


def test_scalar_equivalence_preserves_observable_distinctions():
    db = Database()
    source = db.input(0.0)

    @tracked
    def identity(x):
        return x.value

    @tracked
    def sign(x):
        return math.copysign(1.0, identity(x))

    assert sign(source) == 1.0
    source.value = -0.0
    assert sign(source) == -1.0
    source.value = range(0, 3, 2)
    assert identity(source).stop == 3
    source.value = range(0, 4, 2)
    assert identity(source).stop == 4


@pytest.mark.parametrize("seed", range(8))
def test_random_dag_matches_fresh_evaluation_through_updates_and_eviction(seed):
    rng = random.Random(seed)
    db = Database()
    sources = [db.input(rng.randrange(-10, 10)) for _ in range(6)]
    edges = [(rng.randrange(i), rng.randrange(i)) for i in range(6, 30)]

    @tracked
    def node(index):
        if index < 6:
            return sources[index].value
        a, b = edges[index - 6]
        first = node(a)
        return first + node(b) if first % 2 else first // 2

    def fresh(index):
        if index < 6:
            return sources[index].value
        a, b = edges[index - 6]
        first = fresh(a)
        return first + fresh(b) if first % 2 else first // 2

    run = db.bind(node)
    for _ in range(100):
        sources[rng.randrange(6)].value = rng.randrange(-20, 20)
        for index in rng.sample(range(30), 5):
            assert run(index) == fresh(index)
        if rng.randrange(4) == 0:
            db.prune(max_entries=rng.randrange(15))
