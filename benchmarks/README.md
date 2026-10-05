# Benchmarks

[Measured results](RESULTS.md) cover CPython 3.9–3.14 on the same machine, with
three workload sizes and raw timing samples for every scenario.

## Run the suite

From a checkout, install the library and run:

```bash
python -m pip install .
python benchmarks/bench_engine.py --json benchmark-results.json
```

The suite uses only the standard library and Revlet. Defaults are 200 samples
after 20 warmup calls, sizes of 100, 1,000, and 10,000, and a graph with 32 leaf
queries. Output includes median and p95 latency in microseconds.

For a shorter run:

```bash
python benchmarks/bench_engine.py --sizes 100 1000 --iterations 50 --warmups 10
```

## What each scenario measures

| Scenario | Timed operation |
| --- | --- |
| fresh | Calculate a scalar result directly, without caching. |
| hit | Read an already cached result with unchanged inputs. |
| recompute | Recalculate after changing the input. |
| cutoff_fresh | Calculate the parity-based result directly. |
| cutoff | Validate after the input changes but its parity stays equal. |
| unrelated | Validate after changing an input the query does not read. |
| update_and_read | Write the input and recalculate, including write overhead. |
| list_scan | Sum a plain list with a Python loop. |
| view_scan | Sum the same values through a protected view. |
| dag_fresh | Recalculate every graph leaf and sum their results. |
| dag_sparse | Update one cached leaf and recalculate the graph result. |

Scalar workloads perform `size` additions. Collection workloads visit `size`
elements. Each graph leaf performs `size` additions; one leaf changes before
each graph sample. Use `--fanout` to change the number of leaves.

The fresh and incremental pairs compute the same results. The cutoff scenario
uses exact integer equality after a parity calculation. Every sample checks its
answer against a direct formula outside the timed section. Cached scenarios also
check the number of executed queries: zero for a hit or unrelated update, one for
cutoff, and two for recomputation or a sparse graph update.

Setup and writes are outside the timed section except in `update_and_read`.
Garbage collection stays enabled; each scenario starts after a collection and
warmup. Samples use `time.perf_counter_ns()`.

## Read and reproduce the report

The JSON output includes all raw samples, median/p95/minimum latency, query
execution counts, interpreter and processor details, parameters, and SHA-256
hashes of the benchmark and runtime sources.

Render your own run as Markdown:

```bash
python benchmarks/report.py benchmark-results.json --output benchmark-report.md
```

To reproduce the published matrix, run the default command sequentially under
each listed interpreter, saving one JSON file per interpreter. Then combine the
files with `report.py`. The report tool checks that the code, parameters, and
machine match before comparing runs.

Regenerate the included report from its raw data:

```bash
python benchmarks/report.py benchmarks/results/cpython-*.json --output benchmarks/RESULTS.md
```

Small calculations can be cheaper to execute directly than to cache. Protected
views add work per element, and graph validation adds work per dependency. The
[result tables](RESULTS.md) show these costs alongside the savings from reusing
calculations. The suite measures single-threaded latency; it does not measure
lock contention, native-array operations, or memory consumption.
