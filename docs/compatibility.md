# Runtime and typing compatibility

## Runtime

The minimum runtime is Python 3.9. Runtime modules use compatible syntax and
standard-library interfaces, and the distribution has no third-party runtime
dependencies. Generic runtime aliases permit `Input[int, int]` and adapter
subclass annotations without requiring newer Python syntax.

CI covers CPython 3.9–3.14 and includes Windows and macOS installation tests.
PyPy and free-threaded CPython builds are not currently certified.

## Type stubs

The public `__init__.pyi` ships beside its runtime module and `py.typed`. It uses
Python 3.12 type aliases and generic parameter syntax, including `ParamSpec`
parameters that preserve query call signatures.

The runtime does not parse stubs, but type tools do. The
[typing specification](https://typing.python.org/en/latest/spec/distributing.html#syntax)
recommends syntax compatible with supported parsers for broadly portable stubs.
This project explicitly chooses modern stub syntax while retaining Python 3.9
runtime support. It does **not** promise compatibility with every older checker
or a checker that rejects this grammar for an older target version.

The supported development check configuration uses Python 3.12 as its target.
Run these tools in a separate Python 3.12+ environment when deploying on Python
3.9. Such a check will not detect every use of newer standard-library APIs:
actual runtime compatibility tests are also required.

## Read interfaces

For common scalar containers, inference distinguishes reads from writes:

```python
items = db.input([1, 2])
# items.value: Sequence[int]
# items.edit(): context manager yielding list[int]
```

The type system cannot generally express recursively transforming an arbitrary
mutable Python type into its read-only interface. Nested or unknown container
members therefore widen to `object`, rather than falsely retaining writable
`list` or `dict` types.

For precise custom shapes, supply a typed `ValueAdapter[Stored, Read]`. Annotate
query functions with their intended read interfaces when that interface already
describes the returned value. Custom query result conversions should use an
explicit `result_adapter`; runtime database registration alone cannot teach a
type checker the result type.

## Checks

- Ruff selects Python 3.9 for runtime files and Python 3.12 for stubs.
- Mypy checks public stubs, internal implementation modules, and caller fixtures.
- Pyright checks the caller fixtures with a Python 3.12 target.
- Stubtest compares public runtime signatures and exports with their declarations.
- Behavioral tests execute the installed package on the CI interpreter matrix.
- Distribution tests verify that the type files are included.

The development lock currently contains mypy 2.4.0 and Pyright 1.1.414. The verified
configuration is recorded in `pyproject.toml`, rather than assuming that all IDE
and checker combinations have identical behavior.
