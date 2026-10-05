# User guide

## Define a query

Create inputs in a database and decorate functions that calculate results from
them. Call the decorated functions normally:

```python
from revlet import Database, tracked

db = Database()
price = db.input(10)
quantity = db.input(3)


@tracked
def subtotal(price, quantity):
    return price.value * quantity.value


assert subtotal(price, quantity) == 30
```

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

For a query without input arguments, use `db.bind(query)`:

```python
@tracked
def invoice():
    return subtotal(price, quantity)


calculate_invoice = db.bind(invoice)
assert calculate_invoice() == 30
```

Each database keeps its own cache, so the same query definition can be used
across independent databases.

## Query arguments

Ordinary keys support exact built-in scalar types, tuples, and frozensets.
Integers, booleans, and floats remain distinct; floating-point keys preserve
signed zero and bit patterns. Positional/default/keyword binding is normalized,
and observable order in `**kwargs` is preserved. Queries must not distinguish
otherwise equivalent value arguments by Python object identity.

For an application type, register a function that identifies its data. Here a
document owns a text input; reads of that input track changes to the document:

```python
class Document:
    def __init__(self, database, text):
        self.__revlet_database__ = database
        self.text = database.input(text)


db.register_key(Document, lambda document: document.text)


@tracked
def word_count(document):
    return len(document.text.value.split())


document = Document(db, "hello world")
assert word_count(document) == 2
document.text.value = "hello"
assert word_count(document) == 1
```

A key adapter returns supported stable key data, including owned handles. It
must be pure. Hashability is insufficient evidence of stability. Changing data
behind a stable key still requires an observed dependency. Registration uses
exact types and cannot be replaced during the database's lifetime.
Tracked methods can use the same ownership attribute and a key registered for
their instance's type.

## Inputs and editing

`db.input(value, adapter=...)` constructs an owned input. `input.value` records
a dependency and returns its read interface; assignment replaces the stored value.
Replacement reports a possible change even for an equal value.
The read-only `input.changed_at` stamp observes that input as a dependency as well.

`with input.edit() as writable:` grants controlled in-place access. Once access
might have occurred, changes are registered on normal or exceptional exit,
including adapter failures. Stable adapters require replacement instead.
Nested edits of different inputs are allowed; overlapping edits of one input
and replacement during that input's editing scope are rejected.

Use `with db.write():` to group several changes. Other threads see the completed
group when they next read through Revlet:

```python
with db.write():
    price.value = 12
    quantity.value = 4
```

The writer can call queries against current data. These evaluations do not use
or publish ordinary cached entries. Other threads cannot observe unfinished
writes through managed access. Changes made before an exception remain applied.
A cached query cannot initiate managed writes, eviction, or adapter registration.
A database write scope does not grant raw input access by itself; use each
input's editing scope for in-place mutations.

## Read-only views and copies

Built-in lists, tuples, dictionaries, sets, frozensets, and bytearrays use lazy
views. Nested members are adapted when accessed. Unknown mutable types require a
value adapter; they are never silently exposed as ordinary writable objects.

A borrowed view expires when a managed write starts, even when the write affects
an unrelated input. It also expires after cache reclamation. Reacquire the input
or query result to obtain a current view. Accessing an expired view raises
`StaleViewError`. Iterators check validity as they advance. A writer's temporary
view may reflect subsequent raw edits within the same editing scope; make an
explicit copy when a stable value is required.

`copy_value(view)` explicitly deep-copies supported built-in graphs, preserving
cycles, shared references, and built-in container types. A shallow `list(view)`
still contains borrowed nested members. Custom read interfaces delegate copying
to their own `__deepcopy__` implementation; adapters can provide a more suitable
native copying operation.

```python
from revlet import copy_value

items = db.input([[1, 2]])
snapshot = copy_value(items.value)
with items.edit() as values:
    values[0].append(3)
assert snapshot == [[1, 2]]
assert copy_value(items.value) == [[1, 2, 3]]
```

If you still hold the original mutable object passed to `db.input()`, update it
through the input's editing scope. Mutating it directly bypasses change tracking.
Stop using writable references when their editing scope exits. Views from another
database cannot be used as query results or nested result values.

## Result equivalence

`@tracked(equivalent=callback)` overrides an adapter's equivalence operation.
The callback accepts old and new **read interfaces**, returns an actual `bool`,
and must be pure. Return `True` only when callers can use the old result in place
of the new one. For floating-point results, you can choose your own tolerance:

```python
@tracked(equivalent=lambda old, new: abs(old - new) < 0.01)
def reading(source):
    return source.value


sensor = db.input(1.0)
assert reading(sensor) == 1.0
sensor.value = 1.005
assert reading(sensor) == 1.0  # Reuses the previous value within the tolerance.
sensor.value = 1.02
assert reading(sensor) == 1.02
```

On equivalence, the engine retains the old published value and its change stamp,
while recording the newly observed dependencies. Approximate comparisons remain
anchored to that published value. Comparator exceptions propagate and do not
publish a partial memo.

Early cutoff requires an adapter with `stable = True`: the old stored value
must stay unchanged for the comparison to be meaningful. Built-in mutable
container results recompute even when a custom comparator is supplied.

## Value adapters

Subclass `ValueAdapter[Stored, Read]`:

- `read(value, guard)` returns a protected read interface.
- `edit(value)` optionally returns a context manager yielding writable storage.
- `equivalent(old, new)` returns whether the previous result can be reused; the
  default returns `False`.
- Set `stable = True` only when stored values stay unchanged across managed writes.
  Returning an immutable projection of mutable stored data is insufficient:
  the stored value itself must remain unchanged.

For mutable native storage, hold `with guard:` around each complete read operation,
including the native call. Use `guard.protect(member)` for nested members. Returning
a native object that ignores the guard does not enforce the view lifetime.
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
external_catalog = {"price": 10}
version = db.dependency(name="external-catalog")


@tracked
def lookup(version):
    version.observe()
    return external_catalog["price"]


assert lookup(version) == 10
with version.changing():
    external_catalog["price"] = 12
assert lookup(version) == 12
```

`token.changing()` coordinates the external write with managed readers and
registers possible changes even on failure. `token.changed()` reports a change
that the provider coordinated independently. Notifications alone cannot repair
unreported changes or a race between an external write and its notification.
Connect your file watcher or refresh loop to `token.changing()` when updating
the external data.

## Cancellation and concurrency

```python
from revlet import CancellationToken

token = CancellationToken()
with token.scope():
    result = calculate_invoice()
```

Another thread may call `token.cancel()`. A token can also receive a parent
token. Checks occur before lock entry, while waiting, during validation, and
before publication. Call `check_cancelled()` inside long loops to respond while
they run. Cancellation raises `CancelledError` at a checkpoint.

One database serializes synchronous operations using a reentrant lock. Concurrent
callers reuse a successful completed memo; cancellation of a waiting caller does
not cancel its peer. Queries in distinct databases can execute independently.
Do not wait inside a query for another thread to enter the same database.

Use `await asyncio.to_thread(bound_query)` to call a synchronous query
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
callback selects iteration, convergence, and its final return value. Set the
iteration limit and convergence condition appropriate for your calculation in
that callback. These provisional results are kept out of the normal query cache.

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

## Troubleshooting

| Error | Cause and next step |
| --- | --- |
| `OwnershipError` | A query has no database, or it mixes databases. Pass an input from the intended database or use `db.bind(query)`; keep nested reads in that database. |
| `ReadOnlyError` | A write was attempted through a read-only view. Use `with input.edit():` or copy the result with `copy_value()`. |
| `StaleViewError` | A write or cache operation invalidated a borrowed view. Read the input or query again to get a current view. |
| `MutationError` | An operation conflicts with an active query, read guard, or editing scope. Perform writes and cache changes outside the query and finish active scopes before closing the database. |
| `AdapterError` | A value, key, or callback does not meet its interface requirements. Supply a value/key adapter for unsupported types and check custom callback return types and access to managed state. |
| `CycleError` | Queries called each other recursively. Inspect `error.calls` to find the cycle, or supply a solver when the calculation has a well-defined cyclic solution. |
| `CancelledError` | A cancellation checkpoint observed a cancelled token. Handle it at the request boundary; create a new token for another request. |
| `ClosedDatabaseError` | Code accessed a closed database. Create a new database or keep the existing one open until its queries and views are no longer needed. |

These exceptions inherit from `RevletError`. Exceptions raised by your own query
functions propagate with their original types and tracebacks.
