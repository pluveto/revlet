# Contributing

## Development environment

Use Python 3.12+ for development tooling:

```bash
uv sync --python 3.12 --locked
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync pyright
uv run --no-sync python -m mypy.stubtest revlet
uv run --no-sync pytest
uv run --no-sync python -m build
uv run --no-sync python scripts/check_dist.py
uv run --no-sync twine check --strict dist/*
```

Runtime dependencies are empty. Tooling is confined to development groups.
Commit `uv.lock` when changing development dependencies.

## Code and public types

- Runtime source and examples must execute on Python 3.9.
- Public declarations in `src/revlet/__init__.pyi` deliberately use Python 3.12
  typing syntax. See [compatibility.md](docs/compatibility.md) for its limitations.
- Internal implementation modules have annotations and are checked independently
  of the public stub. Do not add a stub that silently hides an unchecked implementation.
- Runtime generic aliases support annotations such as `Input[int, int]` on Python 3.9.
- Document observable behavior in English, including errors and adapter obligations.
- Prefer a narrow correctness contract over an implicit business policy.

## Behavioral verification

Tests import the installed distribution without inserting `src/` into `sys.path`.
The CI matrix installs the same built wheel on CPython 3.9–3.14, including Windows
and macOS jobs. The wheel is built from the sdist. Type tools run against the
modern stubs and caller fixtures.

Changes to validation or publication should include a reproducer that fails on
the old behavior. The randomized DAG tests compare incremental results with fresh
evaluation through updates, branch changes, and cache eviction. Concurrency tests
coordinate with events and barriers rather than relying on scheduling delays.

For local compatibility checks, use separate environments rather than repeatedly
replacing your development environment. Build the sdist and wheel, install the
wheel into the target environment, and run the behavioral suite there.

## Release acceptance

Follow the [release procedure](docs/releasing.md). Review API compatibility, pass
the complete CI matrix and distribution checks, and review representative workload
benchmarks. Release checks deliberately fail while required metadata is missing.
A green unit suite is evidence about tested behavior, not a claim of universal
threading, adapter, or mathematical solver correctness.
