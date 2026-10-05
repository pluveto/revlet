# Implementation and boundaries

## Core algorithm

Each database owns an input revision, monotonically increasing change stamps,
interned call identities, and retained memo payloads. Revisions advance once at
the outermost write scope's exit when a possible change has been registered.
Change stamps also distinguish successful publications within a revision.

A memo contains the published value and adapter, ordered dependency observations,
a validation revision, and a result change stamp. On a later revision:

1. Validate dependencies in their original observation order.
2. Recursively bring child queries up to date before comparing their change stamps.
3. Stop at the first changed dependency and execute the query again.
4. Capture dependencies into a temporary frame.
5. Publish only after the function, adaptation, comparison, and cancellation
   checkpoint complete successfully.
6. If valid equivalence proves substitution, retain the previous result and change
   stamp. Always replace the dependency list with the new observations.

Ordered validation avoids evaluating an obsolete branch after its controlling
dependency has changed. Same-revision hits avoid revalidating the graph.

## Read and write coordination

The first implementation uses a database-local reentrant lock. It holds a root's
consistent read scope across nested calls, and a write scope across its entire
body. Runtime context variables carry only execution-local frames and cancellation;
there is no default global database or decorator-owned memo table.

Frames have an execution identity and active lifetime. Copied contexts cannot
continue using a retired frame. Same-thread reentry by a different asyncio task
is rejected. Foreign database reads from queries are rejected before acquiring
a foreign lock, avoiding deadlock between opposing invalid cross-database reads.

Queries made by a writer use separate temporary node identities. They neither
reuse nor replace ordinary memo payloads. Cleanup and change publication happen
on exceptional exits as well as normal ones.

## Aliases and comparison evidence

The implementation does not traverse whole object graphs to discover every
shared allocation. Mutable input readers and mutable result producers observe a
conservative database-local alias dependency. Granting in-place editing marks
this dependency changed.

Consequently, an edit may recompute readers of other mutable inputs even when
those inputs are actually independent. This is an explicit correctness fallback.
Scalar replacement does not incur this broad invalidation. A later adapter
capability for precise storage provenance can improve precision without weakening
the contract.

Mutable container adapters do not provide stable old comparison anchors.
Custom comparators alone cannot enable unsafe cutoff on aliased old storage.
Stable adapters make a stronger promise about their stored values and require
input replacement rather than editing.

Views hold a write epoch and an operation guard. They expire on writes and
reclamation. Reacquiring a validated cached result creates a current outer guard;
nested borrowed views can be reused only when their source's change stamp still
justifies the old storage. Unknown or expired temporary storage is rejected.

## Failure and reclamation

Failed computations are not published. If a parent catches a failed query, it
and its dependents remain uncacheable for that execution. This is conservative;
a future failure-result mechanism could prove more reuse under an explicit
failure contract.

Interned nodes use weak references; retained payloads use a database-local
ordered cache. Dependencies hold node identities alive as needed. Eviction removes
the payload and its outgoing observations, so a retained parent must re-evaluate
an evicted child when validation is necessary. Missing payloads cannot masquerade
as successful entries or prove equality with discarded values.

The core does not retain provisional cycle results in the ordinary cache. An
explicit solver runs under the same consistent read scope and publishes only its
final declared result with observed external dependencies.

## Current implementation limits

These are implementation decisions, not universal incremental-computation laws:

- Synchronous, eager query execution; serialized operations within each database.
- Recursive dependency validation and Python call-stack limits.
- Conservative alias invalidation and no implicit memory budget.
- Unknown mutable types require adapters; no built-in NumPy integration.
- No cross-database dependency graph, persistence, automatic rollback, retries,
  async query runtime, or bundled mathematical cycle solver.
- Modern public stubs target Python 3.12 tooling while runtime supports Python 3.9.
- Approximate equivalence and solver convergence are provider obligations.
- No claim of protection against raw aliases or native-code bypasses.

These boundaries are covered by documentation and focused tests. Native code
remains an option after workload measurements identify a useful target.
