"""Concurrency, cooperative cancellation, external dependencies, and cleanup."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from revlet import (
    CancellationToken,
    CancelledError,
    ClosedDatabaseError,
    Database,
    MutationError,
    OwnershipError,
    check_cancelled,
    tracked,
)


def test_concurrent_callers_share_completed_work():
    db = Database()
    source = db.input(1)
    entered, finish = threading.Event(), threading.Event()
    calls = []

    @tracked
    def calculate(x):
        calls.append(1)
        entered.set()
        assert finish.wait(5)
        return x.value + 1

    with ThreadPoolExecutor(max_workers=4) as pool:
        first = pool.submit(calculate, source)
        try:
            assert entered.wait(5)
            rest = [pool.submit(calculate, source) for _ in range(3)]
        finally:
            finish.set()
        assert first.result(timeout=5) == 2
        assert [future.result(timeout=5) for future in rest] == [2, 2, 2]
    assert calls == [1]


def test_reader_cannot_observe_half_finished_multi_input_write():
    db = Database()
    left, right = db.input(1), db.input(2)
    started = threading.Event()

    @tracked
    def total():
        return left.value + right.value

    def read():
        started.set()
        return db.bind(total)()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with db.write():
            left.value = 10
            pending = pool.submit(read)
            assert started.wait(5)
            assert not pending.done()
            right.value = 20
        assert pending.result(timeout=5) == 30


def test_cancel_waiter_does_not_cancel_shared_computation():
    db = Database()
    source = db.input(1)
    entered, finish, waiting = threading.Event(), threading.Event(), threading.Event()
    token = CancellationToken()

    @tracked
    def calculate(x):
        entered.set()
        assert finish.wait(5)
        return x.value

    def waiter():
        with token.scope():
            waiting.set()
            return calculate(source)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(calculate, source)
        try:
            assert entered.wait(5)
            second = pool.submit(waiter)
            assert waiting.wait(5)
            token.cancel()
            with pytest.raises(CancelledError):
                second.result(timeout=5)
        finally:
            finish.set()
        assert first.result(timeout=5) == 1
    assert calculate(source) == 1


def test_cancellation_before_publication_discards_partial_work():
    db = Database()
    source = db.input(1)
    token = CancellationToken()

    @tracked
    def calculate(x):
        token.cancel()
        return x.value

    with pytest.raises(CancelledError):
        with token.scope():
            calculate(source)
    assert db.cache_info().entries == 0
    assert calculate(source) == 1


def test_nested_cancellation_and_edit_cleanup():
    db = Database()
    source = db.input([1])
    parent = CancellationToken()
    child = CancellationToken(parent)
    with pytest.raises(CancelledError):
        with child.scope():
            with source.edit() as values:
                values.append(2)
                parent.cancel()
                check_cancelled()
    assert source.value == [1, 2]
    assert db.revision == 1


def test_external_dependency_coordinates_changes():
    db = Database()
    dependency = db.dependency(name="external")
    external = {"value": 1}
    calls = []

    @tracked
    def read(token):
        calls.append(1)
        token.observe()
        return external["value"]

    assert read(dependency) == read(dependency) == 1
    with dependency.changing():
        external["value"] = 2
        assert read(dependency) == 2
    assert read(dependency) == 2
    external["value"] = 3
    dependency.changed()
    assert read(dependency) == 3
    assert len(calls) == 4


def test_async_tasks_cannot_reenter_another_tasks_write_scope():
    async def scenario():
        db = Database()
        value = db.input(1)

        async def other_task():
            with pytest.raises(MutationError, match="across tasks"):
                return value.value

        with db.write():
            await asyncio.create_task(other_task())
        assert value.value == 1

    asyncio.run(scenario())


def test_async_functions_are_rejected_and_thread_offload_works():
    async def calculate():
        return 1

    with pytest.raises(TypeError, match="synchronous"):
        tracked(calculate)

    db = Database()

    @tracked
    def eager():
        return 2

    async def scenario():
        return await asyncio.to_thread(db.bind(eager))

    assert asyncio.run(scenario()) == 2


def test_close_is_idempotent_and_rejects_later_access():
    with Database() as db:
        source = db.input(1)
    db.close()
    with pytest.raises(ClosedDatabaseError):
        _ = source.value
    with pytest.raises(ClosedDatabaseError):
        db.input(2)


def test_close_during_edit_is_rejected():
    db = Database()
    with db.input([]).edit():
        with pytest.raises(MutationError):
            db.close()
    db.close()


def test_conflicting_cross_database_reads_fail_before_taking_foreign_locks():
    one, two = Database(), Database()
    left, right = one.input(1), two.input(2)
    barrier = threading.Barrier(2)
    failures = []

    @tracked
    def first(x):
        barrier.wait(timeout=5)
        return right.value

    @tracked
    def second(x):
        barrier.wait(timeout=5)
        return left.value

    def run(query, value):
        try:
            query(value)
        except OwnershipError as error:
            failures.append(error)

    threads = [
        threading.Thread(target=run, args=(first, left), daemon=True),
        threading.Thread(target=run, args=(second, right), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(failures) == 2
