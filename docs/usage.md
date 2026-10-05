# Usage and API contracts

## Query definitions and ownership

`@tracked` accepts synchronous, eager functions. A query must compute from its
arguments and observed managed state. Changing environment variables, files,
clocks, random state, or captured mutable configuration require an explicit input
or dependency token. A cache hit can skip the function entirely: do not rely on
side effects being executed on every call.

`db.revision`, `db.cache_info()`, and `db.dependencies(...)` are diagnostic
snapshots, not tracked inputs. Inspect them outside query computations. Represent
application state that affects a result with an input or dependency token.

Owned inputs and tokens in arguments identify the root database. Tuples and
frozensets can contain owned handles. Nested queries inherit the active database.
A custom argument can expose a stable `__revlet_database__` attribute. Mixed
owners and hidden reads from another database raise `OwnershipError`.

`db.bind(query)` returns a normal callable for roots without owned arguments.
A query definition does not store database cache state. Bound methods are
supported when the instance supplies ownership and a registered stable key.

Ordinary keys support exact built-in scalar types, tuples, and frozensets.
Integers, booleans, and floats remain distinct; floating-point keys preserve
signed zero and bit patterns. Positional/default/keyword binding is normalized,
and observable order in `**kwargs` is preserved. Queries must not distinguish
otherwise equivalent value arguments by Python object identity.

For application argument types:

```python
db.register_key(Document, lambda document: document.input_handle)
```

A key adapter returns supported stable key data, including owned handles. It
must be pure. Hashability is insufficient evidence of stability. Changing data
behind a stable key still requires an observed dependency. Registration uses
exact types and cannot be replaced during the database's lifetime.

## Inputs and editing

`db.input(value, adapter=...)` constructs an owned input. `input.value` records
a dependency and returns its read interface; assignment replaces the stored value.
Replacement conservatively reports a change even for an equal value.
The read-only `input.changed_at` stamp observes that input as a dependency as well.

`with input.edit() as writable:` grants controlled in-place access. Once access
might have occurred, changes are registered on normal or exceptional exit,
including adapter failures. Stable adapters require replacement instead.
Nested edits of different inputs are allowed; overlapping edits of one input
and replacement during that input's editing scope are rejected.

`with db.write():` groups writes into a single revision publication:

```python
with db.write():
    price.value = 12
    quantity.value = 4
```

The writer can call queries against current data. These evaluations do not use
or publish ordinary cached entries. Other threads cannot observe unfinished
writes through managed access. No scope provides implicit rollback. A cached
query cannot initiate managed writes, eviction, or adapter registration.
A database write scope does not grant raw input access by itself; use each
input's editing scope for in-place mutations.

## Read-only views and copies

Built-in lists, tuples, dictionaries, sets, frozensets, and bytearrays use lazy
views. Nested members are adapted when accessed. Unknown mutable types require a
value adapter; they are never silently exposed as ordinary writable objects.

A borrowed view expires when a managed write starts, even when the write affects
an unrelated input. It also expires after cache reclamation. Reacquire the input
or query result to obtain a current view. This deliberately avoids suggesting
that a zero-copy view is a historical snapshot. Iterators check the lease as
they advance. A writer's temporary view may reflect subsequent raw edits within
the same editing scope; make an explicit copy when a stable value is required.

`copy_value(view)` explicitly deep-copies supported built-in graphs, preserving
cycles, shared references, and built-in container types. A shallow `list(view)`
still contains borrowed nested members. Custom read interfaces delegate copying
to their own `__deepcopy__` implementation; adapters can provide a more suitable
native copying operation.

Original writable aliases and deliberately accessed private attributes are not
policed. All writes through aliases must follow the managed editing contract.
A writable reference must not be used after its editing scope exits. Borrowed
views from another database cannot be embedded as protected query data.

## Result equivalence

`@tracked(equivalent=callback)` overrides an adapter's equivalence operation.
The callback accepts old and new **read interfaces**, returns an actual `bool`,
and must be pure. It must justify substituting the old result for the new one in
downstream queries. Domain tolerances belong to the application.

On equivalence, the engine retains the old published value and its change stamp,
while recording the newly observed dependencies. Approximate comparisons remain
anchored to that published value. Comparator exceptions propagate and do not
publish a partial memo.

Comparison is only allowed when the adapter guarantees that the old stored value
remains a stable comparison basis. Built-in mutable container results do not
make that promise, even if a custom comparator was supplied. This prevents
shared-storage mutation from comparing a changed object with itself.

## Value adapters

Subclass `ValueAdapter[Stored, Read]`:

- `read(value, guard)` returns the promised protected read interface.
- `edit(value)` optionally returns a context manager yielding writable storage.
- `equivalent(old, new)` optionally proves substitution. Its default is false.
- `stable = True` promises that stored published values remain unchanged across
  managed writes, so they can be used later as comparison anchors. Merely returning
  an immutable projection of mutable stored data does not establish this promise.

For mutable native storage, hold `with guard:` around each complete read operation,
including the native call. Use `guard.protect(member)` for nested members. Returning
a native object that ignores the guard does not enforce the view lifetime.
Read guards provide coordination, not a sandbox against unsafe native code.
Read-adapter callbacks cannot read additional managed state, call queries, or
initiate managed writes. Accessing their supplied guard is supported.

Use `db.input(value, adapter=adapter)` and
`@tracked(result_adapter=adapter)` to make custom conversions explicit and typed.
`db.register_adapter(Type, adapter)` also supports database-local dynamic
adaptation and nested members. It matches exact types and cannot replace built-in
adapters. Adapters must not change semantics or captured configuration after
registration without a corresponding dependency contract.

See [adapters.py](../examples/adapters.py) for an immutable custom value.

## External state

```python
version = db.dependency(name="external-catalog")


@tracked
def lookup(version):
    version.observe()
    return external_catalog["price"]


with version.changing():
    external_catalog["price"] = 12
```

`token.changing()` coordinates the external write with managed readers and
registers possible changes even on failure. `token.changed()` reports a change
that the provider coordinated independently. Notifications alone cannot repair
unreported changes or a race between an external write and its notification.
The provider owns watching, polling, refresh intervals, and persistence.

## Cancellation and concurrency

```python
token = CancellationToken()
with token.scope():
    result = calculate()
```

Another thread may call `token.cancel()`. A token can also receive a parent
token. Checks occur before lock entry, while waiting, during validation, and
before publication. Long loops should call `check_cancelled()`. Arbitrary Python
or C work is not forcibly interrupted.

One database serializes synchronous operations using a reentrant lock. Concurrent
callers reuse a successful completed memo; cancellation of a waiting caller does
not cancel its peer. Queries in distinct databases can execute independently.
Do not wait inside a query for another thread to enter the same database.

Async query functions are currently rejected. Use `await asyncio.to_thread(bound_query)`
for an async application. Cancelling the asyncio task alone does not stop its
worker thread; propagate cancellation through an explicit token. Synchronous
database scopes must not be shared across tasks or held across an `await`.

## Cycles and failures

An unresolved cycle raises `CycleError` with a tuple of structured `QueryCall`
objects: name, arguments, keyword arguments, and stable call identity. The repeated
call appears at both ends of the path.

`@tracked(solver=solve)` connects an explicit solver. The callback receives a
`CycleContext` whose `evaluate({call: provisional_value})` evaluates the original
query with caller-selected assumptions about calls in that cycle. These
evaluations collect dependencies without publishing provisional memos. The
callback selects iteration, convergence, and its final return value. The engine
does not prove the solver's domain mathematics or impose an iteration limit.

Solver contexts are only usable during their callback. Newly encountered cycles
without supplied assumptions still raise. See [cycles.py](../examples/cycles.py).

Escaping failures propagate with their original type and traceback. Temporary
frames are cleaned up. A parent that catches a failed child is conservatively
uncacheable; observed dependencies are preserved for enclosing computations.
Applications can return domain error values explicitly when such outcomes should
be ordinary cacheable data.

## Cache lifecycle and diagnostics

- `db.cache_info()`: revision, retained entries, live node identities, hits,
  validations, function executions, and evictions.
- `db.dependencies(query, *args, **kwargs)`: direct dependencies from the last
  successful retained execution. Internal conservative alias dependencies are omitted.
- `db.prune(max_entries=N)`: explicitly evict least recently used payloads until
  the caller's entry budget is met; returns the number evicted.
- `db.clear_cache()`: evict all retained payloads; returns the number evicted.
- `db.close()`: release engine caches and registrations. Further managed access fails.
- `with Database() as db:`: close on exit.

There is no implicit capacity limit. Callers choose when to prune. Entry counts
are not byte budgets, and dependency identities can remain alive while another
entry references them. Evicted dependencies are recomputed before dependent
entries can be validated.
