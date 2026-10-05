# Contributing

## Report a bug or suggest a change

Open an [issue](https://github.com/pluveto/revlet/issues) with a small example,
the result you expected, and what happened instead. Include your Python and
Revlet versions. For performance issues, include the input size and update pattern.

For security reports, use the contact in [SECURITY.md](SECURITY.md).

## Work on a change

Fork the repository, clone your fork, and use Python 3.12+ with `uv`:

```bash
uv sync --python 3.12 --locked
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync pyright
uv run --no-sync python -m mypy.stubtest revlet
```

Runtime code supports Python 3.9+. Public type declarations live in
`src/revlet/__init__.pyi` and use Python 3.12 syntax. When changing an API, update
both its implementation and its type declaration.

For a bug fix, add a test that reproduces the problem. Update the relevant example
or user guide when behavior changes. If you change development dependencies,
update `uv.lock` with `uv lock`.

Submit a pull request describing the change and how you checked it. CI runs the
tests on Python 3.9–3.14, including Windows and macOS jobs.

## Check packaging changes

Use an empty `dist/` directory, then run:

```bash
uv run --no-sync python -m build
uv run --no-sync python scripts/check_dist.py
uv run --no-sync twine check --strict dist/*
```

These commands build the source archive and wheel, then check package contents,
type files, license metadata, and the README rendering.
