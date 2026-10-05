# Releasing revlet

This procedure prepares and publishes the same wheel that passes the compatibility
matrix. Building locally or pushing a commit does not publish a package.

## Repository setup (once)

1. The project is MIT licensed, maintained by `pluveto`, and hosted at
   [pluveto/revlet](https://github.com/pluveto/revlet). Keep the license file and
   package metadata consistent when preparing a release.
2. Enable Actions on the repository. Set branch
   protection to require the quality job and every compatibility job. Protect
   release tags from moving or being deleted.
3. Create GitHub environments named `testpypi` and `pypi`. Restrict deployments to
   version tags and configure the release reviewers appropriate for the project.
4. Configure a pending Trusted Publisher on each index, using the final GitHub
   owner/repository, workflow filename `release.yml`, and the matching environment.
   Follow the [PyPI instructions](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
   Confirm that the project name can be registered before creating a release tag.
5. Enable GitHub private vulnerability reporting and complete the reporting details
   in `SECURITY.md` before publication.

## Prepare a version

- Set the version in `pyproject.toml`, the single source for distribution versions.
  Applications can read it with `importlib.metadata.version("revlet")`.
- Write a changelog entry and migration instructions for any incompatible change.
  Replace the entry's pending-release label with the release date at publication.
- During 0.x, incompatible public API changes increment the minor version; patch
  releases preserve documented interfaces. Private implementation modules are excluded.
- Update `uv.lock` with `uv lock`. Review dependency and pinned GitHub Action changes.
- Run the documented examples and representative workload benchmarks. Review the
  mutation, aliasing, adapter, and solver contracts for changes affecting correctness.

## Local acceptance

Use Python 3.12+ for tooling. Start with an empty output directory; do not mix
artifacts from older builds.

```bash
uv sync --python 3.12 --locked
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync pyright
uv run --no-sync python -m mypy.stubtest revlet
uv run --no-sync pytest
uv run --no-sync python -m build
uv run --no-sync python scripts/check_dist.py --tag v0.1.0
uv run --no-sync twine check --strict dist/*
```

`python -m build` builds the sdist first, then builds the wheel from that sdist.
`check_dist.py` checks names and versions, required metadata, the included license,
zero runtime dependencies, pure Python wheel tags, Python 3.9 source grammar, and
the exact source/stub bytes in both archives. It prints SHA-256 hashes and rejects
extra artifacts. The sdist includes tests, examples, documentation, release tools,
and the development lockfile.

The CI compatibility matrix installs this wheel into clean environments. Linux
covers CPython 3.9–3.14; Windows and macOS cover 3.9 and 3.14. Each job runs the
behavioral tests and examples. Runtime importability alone does not certify an
older type checker: the public stubs intentionally use Python 3.12 syntax.

## Publish

1. Commit the reviewed release and wait for the complete CI matrix to pass.
2. Create and push an annotated tag matching `v` plus the project version.
3. Dispatch the **Release** workflow at that tag with `repository=testpypi`.
   The GitHub CLI can select a tag explicitly:

   ```bash
   gh workflow run release.yml --ref v0.1.0 --field repository=testpypi
   ```

4. Review that run and install the TestPyPI package in a clean environment:

   ```bash
   python -m pip install --index-url https://test.pypi.org/simple/ --no-deps revlet==0.1.0
   python -c "from revlet import Database, tracked; print(Database().revision)"
   ```

5. Dispatch the same workflow at the same tag with `repository=pypi`. The workflow
   reruns all gates and publishes only that run's tested archives. The publish job
   has an OIDC identity; build and test jobs do not. No long-lived PyPI token is needed.
   See [Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).
6. Verify installation from PyPI, review its rendered README and metadata, and
   create a GitHub release using the changelog entry. Keep the workflow's artifact
   hashes for diagnosis.

Tags alone do not trigger publishing. A branch dispatch fails before the build.
Index credentials, environments, name registration, branch/tag protections, and
remote CI results are external setup; local tests cannot establish them.

## Failed releases

Publication is not a transactional upload of both files. If a network failure
occurs, inspect the index and workflow before retrying; compare available hashes.
Never overwrite or silently replace an existing version. Publish a corrected
version for package defects, and use the index's yank mechanism when appropriate.
The workflow deliberately does not hide duplicate-upload errors with `skip-existing`.
