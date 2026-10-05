# Benchmarks

Run against an installed checkout:

```bash
python benchmarks/bench_engine.py --iterations 2000 --size 10000
```

The script reports median microseconds per operation for direct recomputation,
a warm cache hit, a changed scalar input, and a change with output cutoff.
It also measures iteration through a protected container separately, so the
cost of per-element guarding is visible.

These are local microbenchmarks, not release performance promises. Record the
interpreter, hardware, dataset, and update pattern when comparing revisions.
Representative application workloads should guide native-extension work.
