# Changelog

## 0.1.0 — pending release

Initial public release under the name **revlet**.

### Added

- Independent databases, owned inputs, ordinary tracked functions, and bound roots.
- Recursive dependency validation, dynamic branches, and stable-result early cutoff.
- Lazy read-only container views, explicit editing scopes, and explicit deep copies.
- Custom value adapters, stable key adapters, and result equivalence functions.
- External dependency tokens and caller-supplied cycle solvers.
- Thread coordination, cooperative cancellation, and atomic memo publication.
- Explicit cache pruning, dependency inspection, and database cleanup.
- Python 3.9–3.14 runtime support with no third-party runtime dependencies.
- Bundled Python 3.12 type stubs, examples, and reproducible verification commands.

### Compatibility and scope

- Queries within a database execute synchronously under one lock. Async applications
  can offload synchronous queries to a thread.
- Managed writes invalidate borrowed views. Writes do not provide rollback.
- In-place edits conservatively invalidate readers of potentially aliased storage.
- Native async queries, persistence, automatic eviction, and bundled mathematical
  solvers are outside this release. See [implementation](docs/implementation.md).

During 0.x, patch releases preserve documented public interfaces. Incompatible
changes require a minor version increment and migration notes. Internal modules
and private attributes are not public interfaces.
