# Security

## Reporting

Use [GitHub private vulnerability reporting](https://github.com/pluveto/revlet/security/advisories/new)
for a confidential report. Include the affected version, Python version, operating
system, and a minimal reproducer. Do not include credentials or private production data.

Ordinary correctness bugs can be reported through the
[issue tracker](https://github.com/pluveto/revlet/issues).

## Running application code

Queries, adapters, and cycle solvers execute with your application's permissions.
Use implementations you trust. Read-only views prevent mutation through the public
API; Python private attributes and native extensions can still access underlying
storage. See the [user guide](docs/usage.md#read-only-views-and-copies) for safe
handling of shared mutable data.
