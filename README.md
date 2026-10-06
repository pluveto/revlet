![Minimal necessary computation: the demanded path is recomputed, and unchanged branches stop early.](https://raw.githubusercontent.com/pluveto/0images/master/2026/10/upgit_20261006_1791260205.png)

# revlet

Salsa-inspired incremental computation for Python 3.9+, with no runtime dependencies.

Revlet caches function results and tracks the inputs each function reads. When
an input changes, it recomputes affected queries and reuses results whose
dependencies are unchanged. Each database has its own inputs and cache.

Revlet is independent of the Rust Salsa project.

## Quick start

```bash
python -m pip install revlet
```

```python
from revlet import Database, tracked

db = Database()
price = db.input(10)
quantity = db.input(3)


@tracked
def subtotal(price, quantity):
    return price.value * quantity.value


assert subtotal(price, quantity) == 30
assert subtotal(price, quantity) == 30  # Reuses the completed computation.

price.value = 12
assert subtotal(price, quantity) == 36
```

The inputs identify the database when you call a query. Nested queries use the
same database. For a query without input arguments, bind it once:

```python
@tracked
def invoice():
    return subtotal(price, quantity)


calculate_invoice = db.bind(invoice)
assert calculate_invoice() == 36
```

You can reuse the same query definitions with inputs from different databases.

## Mutable data

```python
items = db.input([1, 2])


@tracked
def total(items):
    return sum(items.value)


with items.edit() as values:
    values.append(3)
    assert total(items) == 6  # Evaluates current edits without using normal caches.

assert total(items) == 6
```

- Reads and query results expose read-only interfaces, including nested containers.
- Writes use property replacement or an explicit editing scope.
- A write scope registers possible changes even if its body raises. It does not roll back.
- Borrowed views expire when a managed write begins. Read the input or query again.
- Use `copy_value(view)` for an explicit independent copy of supported built-in data.
- If you keep the original collection passed to an input, change it through the
  input's editing scope so Revlet can track the update.
- In-place edits conservatively invalidate readers that might share mutable storage.

## Working with larger applications

Use value adapters for custom data types, dependency tokens for external state,
and cancellation tokens for long computations. You can inspect dependencies and
prune caches explicitly. The [user guide](https://github.com/pluveto/revlet/blob/main/docs/usage.md)
covers these APIs and custom cycle solvers.

Queries within one database run synchronously under a shared lock. Separate
databases can run independently. Async applications can call synchronous queries
through `asyncio.to_thread`.

The runtime supports Python 3.9+. Bundled type stubs use Python 3.12 syntax;
see [typing compatibility](https://github.com/pluveto/revlet/blob/main/docs/compatibility.md)
for IDE and type checker setup.

## Documentation

- [User guide](https://github.com/pluveto/revlet/blob/main/docs/usage.md)
- [How caching works](https://github.com/pluveto/revlet/blob/main/docs/implementation.md)
- [Runtime and typing compatibility](https://github.com/pluveto/revlet/blob/main/docs/compatibility.md)
- [Executable examples](https://github.com/pluveto/revlet/blob/main/examples/README.md)
- [Benchmarking](https://github.com/pluveto/revlet/blob/main/benchmarks/README.md)
- [Benchmark results](https://github.com/pluveto/revlet/blob/main/benchmarks/RESULTS.md)
- [Contributing](https://github.com/pluveto/revlet/blob/main/CONTRIBUTING.md)
- [Changelog](https://github.com/pluveto/revlet/blob/main/CHANGELOG.md)

## License

[MIT](https://github.com/pluveto/revlet/blob/main/LICENSE) © 2026 pluveto.
