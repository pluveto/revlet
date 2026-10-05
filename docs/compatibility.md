# Runtime and typing compatibility

## Runtime

Revlet runs on Python 3.9+ and has no third-party runtime dependencies.
The [test suite](https://github.com/pluveto/revlet/actions/workflows/ci.yml) covers:

| Platform | CPython versions |
| --- | --- |
| Linux | 3.9–3.14 |
| Windows | 3.9 and 3.14 |
| macOS | 3.9 and 3.14 |

PyPy and free-threaded CPython are not currently tested.

## IDEs and type checkers

The package includes `.pyi` type stubs and a `py.typed` marker; no separate stub
package is needed. The stubs use Python 3.12 generic syntax and preserve decorated
functions' parameter types.

Use a type checker that understands Python 3.12 syntax. Mypy 2.4.0 and Pyright
1.1.414 are tested with a Python 3.12 target. Older checkers, or configurations
that reject this syntax for an older Python target, may report syntax errors in
the stubs even though the library runs on that interpreter.

If you deploy on Python 3.9–3.11, you can run type checks in a separate Python 3.12+
environment with the checker targeting 3.12. Also run your tests on the deployment
interpreter: a 3.12 type check can accept standard-library APIs absent from older
Python versions.

## Read interfaces

For common scalar containers, inference distinguishes reads from writes:

```python
from revlet import Database

db = Database()
items = db.input([1, 2])
# items.value: Sequence[int]
# items.edit(): context manager yielding list[int]
```

Nested or unknown container members are typed as `object`. The runtime still
protects nested mutable values when you access them.

For more precise custom types, supply a `ValueAdapter[Stored, Read]`. When a query
returns a custom type through an adapter, use `@tracked(result_adapter=adapter)`
so the checker can infer its read interface. Registering an adapter dynamically
with `db.register_adapter(...)` does not change static type inference.

Runtime aliases such as `Input[int, int]` and `ValueAdapter[Stored, Read]` work on
Python 3.9. Your own annotations can use syntax supported by your application.
