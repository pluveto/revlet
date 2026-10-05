# revlet

Salsa-inspired incremental computation for Python 3.9+, with no runtime dependencies.

The synchronous engine provides dynamic dependency tracking, protected value
access, explicit extension interfaces, and database-local caches. This project
is independent of the Rust Salsa project.

The first release is **0.1.0**. During 0.x, incompatible public API changes require
a minor version change and migration notes; patch releases preserve the documented
API. See [compatibility](https://github.com/pluveto/revlet/blob/main/docs/compatibility.md)
for supported runtimes and type tools.

## Quick start

Install from this checkout:

```bash
python -m pip install .
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

Queries are ordinary functions. Owned arguments identify the database, and
nested queries inherit it. For a root with no owned arguments, bind once:

```python
@tracked
def invoice():
    return subtotal(price, quantity)


calculate_invoice = db.bind(invoice)
assert calculate_invoice() == 36
```

Query definitions can be reused across independent databases. No database
inheritance or application-wide default database is required.

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
- External writable aliases must respect the editing contract.
- In-place edits conservatively invalidate readers that might share mutable storage.

## What is implemented

- Transitive lazy validation, dynamic dependency replacement, and early cutoff
  against a stable previously published result.
- Database-local cache identities, Python argument binding, typed built-in keys,
  custom key adapters, and explicit ownership checking.
- Atomic memo publication; failures and cancellation cannot publish partial work.
- Coordinated synchronous queries and writes, multi-input write scopes, and
  cancellation while waiting for another caller.
- External dependency tokens, value adapters, and isolated explicit cycle solvers.
- Explicit cache pruning, cache clearing, dependency inspection, and lifecycle cleanup.
- Python 3.12 syntax in bundled `.pyi` files, with `py.typed` and caller typing checks.

The initial engine serializes operations within one database. Separate databases
can run independently. Async applications can use `asyncio.to_thread`; decorating
an `async def` query is currently rejected.

## Documentation

- [Usage and API contracts](https://github.com/pluveto/revlet/blob/main/docs/usage.md)
- [Algorithm and implementation boundaries](https://github.com/pluveto/revlet/blob/main/docs/implementation.md)
- [Runtime and typing compatibility](https://github.com/pluveto/revlet/blob/main/docs/compatibility.md)
- [Executable examples](https://github.com/pluveto/revlet/blob/main/examples/README.md)
- [Benchmarking](https://github.com/pluveto/revlet/blob/main/benchmarks/README.md)
- [Contributing and verification](https://github.com/pluveto/revlet/blob/main/CONTRIBUTING.md)
- [Changelog](https://github.com/pluveto/revlet/blob/main/CHANGELOG.md)
- [Release procedure](https://github.com/pluveto/revlet/blob/main/docs/releasing.md)

## License

[MIT](https://github.com/pluveto/revlet/blob/main/LICENSE) © 2026 pluveto.
