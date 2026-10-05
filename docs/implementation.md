# How caching works

Revlet is useful when you evaluate related calculations repeatedly while changing
only some of their inputs. This guide explains when a query runs again and what
affects the amount of work it can reuse.

## Reads determine dependencies

When a tracked function reads an input or calls another tracked function, Revlet
records that dependency. A cached call stores its result and the dependencies
observed during its last successful execution.

After an input changes, Revlet checks those dependencies when you next call the
query. It validates nested queries before deciding whether to reuse their callers.
Dependencies follow the branches your function actually takes and are updated
whenever the function runs again.

Reads are checked in their original order. If a branch's condition has changed,
the query runs again before Revlet checks dependencies from that obsolete branch.

## An unchanged result can stop recomputation

```python
from revlet import Database, tracked

db = Database()
count = db.input(11)


@tracked
def bucket(count):
    return count.value // 10


@tracked
def label(count):
    return "Group {}".format(bucket(count))


assert label(count) == "Group 1"
count.value = 12
assert label(count) == "Group 1"  # bucket runs again; label reuses its result.
count.value = 20
assert label(count) == "Group 2"  # Both functions run again.
```

Revlet compares a new result with the previously cached result. When they are
equivalent, it keeps the previous value and can reuse downstream results. The
query's dependencies still update to reflect its latest execution.

You can supply a custom comparison with `@tracked(equivalent=...)`. It should
return `True` only when callers can use the old value in place of the new one.
This requires a result adapter with stable stored values; built-in mutable
containers cannot use this shortcut. See [result equivalence](usage.md#result-equivalence).

## Why editing a collection can cause more work

Inputs can share mutable storage, including nested objects. An in-place edit
therefore invalidates queries that read potentially shared mutable data in the
same database, even when the particular inputs are independent.

Replacing a scalar input affects readers of that input. For workloads with many
independent scalar values, separate inputs give Revlet more opportunities to
reuse computations.

Collection reads return views that check their validity as you access elements.
This adds per-element overhead. The [measured results](../benchmarks/RESULTS.md)
compare plain-list iteration with protected views, alongside scalar and graph
workloads. The [benchmark suite](../benchmarks/README.md) includes the commands
and workload definitions used for those measurements.

## Failed and cancelled calls

A query result enters the cache after computation, adaptation, comparison, and
the final cancellation check succeed. Exceptions propagate to the caller. If a
query catches a child query's failure, that execution remains uncached, so the
next call retries it. You can return an application error value when you want
that outcome to be cacheable.

## Keeping cache memory under control

Each database retains successful results until you prune or clear its cache, or
close it. There is no automatic entry limit. Use `db.prune(max_entries=N)` to evict
the least recently used results, or `db.clear_cache()` to clear them all.

An evicted dependency is recomputed when a caller needs to validate it. Pruning
can therefore increase future computation. Clearing or pruning cached results
also invalidates borrowed views; read the input or query again before using them.

Validation uses Python's call stack. Very deep query chains can reach the
interpreter's recursion limit; consider grouping work into fewer query levels.

See the [user guide](usage.md) for write scopes, cancellation, custom adapters,
and database cleanup.
