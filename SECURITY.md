# Security

## Scope

Revlet runs trusted application code. Read-only views protect the supported public
interfaces; they do not sandbox Python, native extensions, or deliberate access to
private attributes. Applications own the contracts for external aliases, custom
adapters, external state, and cycle solvers.

## Reporting

Use [GitHub private vulnerability reporting](https://github.com/pluveto/revlet/security/advisories/new)
for a confidential report. Include the affected version, Python version, operating
system, and a minimal reproducer. Do not include credentials or private production data.

Ordinary correctness bugs can be reported through the
[issue tracker](https://github.com/pluveto/revlet/issues).
There is no guaranteed response time or long-term support commitment for 0.x.
