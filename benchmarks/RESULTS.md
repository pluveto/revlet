# Benchmark results

Measured with Revlet 0.1.0 on 2026-10-05 (UTC).
All scenarios verified their results on every sample. Cached scenarios also
verified query execution counts. The JSON files linked below contain every
timing sample and the hashes of the benchmark and runtime source files.

## Environment and method

- Processor: AMD Ryzen 9 7950X 16-Core Processor.
- Platform: Linux-7.0.13-arch1-1-x86_64-with-glibc2.44.
- Logical CPUs reported by the OS: 32.
- CPython versions: 3.9.25, 3.10.21, 3.11.16, 3.12.2, 3.13.15, 3.14.7.
- Samples per scenario and size: 200.
- Untimed warmup calls: 20.
- Graph fanout: 32 independently cached leaf queries.
- Garbage collection: enabled.

Interpreters ran sequentially on the same host. Tables show median microseconds
per call. Setup, input updates, checksums, and execution-count checks are outside
the timed section, except that **update + read** includes the managed input write.
The JSON summaries also include p95 and minimum latency.

## Reading the results

For Python 3.12.2 at size 10,000:

- A warm cache hit takes 4.39 µs, compared with 165.21 µs for fresh calculation.
- An affected input update plus its query takes 176.24 µs.
- When the intermediate result stays equal, validation takes 11.34 µs versus 164.09 µs for fresh calculation of the same result.
- Updating one leaf of the graph takes 338.78 µs versus 5273.20 µs to recompute all leaves (fresh/incremental ratio: 15.57).
- Protected collection iteration takes 34012.69 µs versus 118.40 µs for a plain list (287.27 times the cost).

Small calculations can cost less than cache lookup and validation. Protected
collection access adds a check per element. The tables make both costs visible
alongside the work saved by reusing expensive queries. These measurements cover
single-threaded scalar and collection workloads on the host above; they do not
measure lock contention, native-array adapters, or application memory usage.

## Scalar queries

| Python | Size | Fresh | Hit | Recompute | Unrelated update | Update + read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3.9.25 | 100 | 1.79 | 7.65 | 37.16 | 8.51 | 40.31 |
| 3.9.25 | 1000 | 23.00 | 7.26 | 55.38 | 8.34 | 59.60 |
| 3.9.25 | 10000 | 226.38 | 6.59 | 249.54 | 7.66 | 255.47 |
| 3.10.21 | 100 | 1.70 | 7.41 | 35.03 | 7.69 | 36.94 |
| 3.10.21 | 1000 | 21.37 | 6.67 | 51.44 | 7.58 | 55.31 |
| 3.10.21 | 10000 | 217.18 | 6.69 | 244.12 | 7.65 | 247.95 |
| 3.11.16 | 100 | 1.35 | 4.83 | 23.10 | 5.43 | 25.76 |
| 3.11.16 | 1000 | 18.84 | 4.82 | 39.54 | 5.43 | 42.13 |
| 3.11.16 | 10000 | 188.86 | 4.83 | 213.01 | 5.45 | 210.03 |
| 3.12.2 | 100 | 1.21 | 4.42 | 21.65 | 5.02 | 23.68 |
| 3.12.2 | 1000 | 15.64 | 4.38 | 35.06 | 4.93 | 36.70 |
| 3.12.2 | 10000 | 165.21 | 4.39 | 174.01 | 4.93 | 176.24 |
| 3.13.15 | 100 | 1.08 | 4.09 | 19.56 | 4.71 | 21.73 |
| 3.13.15 | 1000 | 14.78 | 4.13 | 32.93 | 4.60 | 35.94 |
| 3.13.15 | 10000 | 160.33 | 4.07 | 176.05 | 4.60 | 190.44 |
| 3.14.7 | 100 | 1.30 | 4.57 | 22.85 | 5.27 | 24.79 |
| 3.14.7 | 1000 | 20.27 | 4.49 | 41.28 | 5.18 | 43.20 |
| 3.14.7 | 10000 | 224.40 | 4.55 | 246.45 | 5.14 | 249.28 |

## Equal-result cutoff

| Python | Size | Fresh | Incremental |
| --- | ---: | ---: | ---: |
| 3.9.25 | 100 | 1.71 | 19.51 |
| 3.9.25 | 1000 | 22.39 | 18.96 |
| 3.9.25 | 10000 | 225.69 | 17.48 |
| 3.10.21 | 100 | 1.50 | 18.10 |
| 3.10.21 | 1000 | 22.10 | 17.17 |
| 3.10.21 | 10000 | 215.92 | 17.40 |
| 3.11.16 | 100 | 1.14 | 12.12 |
| 3.11.16 | 1000 | 17.33 | 12.47 |
| 3.11.16 | 10000 | 195.85 | 12.45 |
| 3.12.2 | 100 | 1.04 | 11.31 |
| 3.12.2 | 1000 | 15.53 | 11.31 |
| 3.12.2 | 10000 | 164.09 | 11.34 |
| 3.13.15 | 100 | 0.90 | 10.37 |
| 3.13.15 | 1000 | 14.02 | 10.24 |
| 3.13.15 | 10000 | 159.79 | 10.52 |
| 3.14.7 | 100 | 1.06 | 11.56 |
| 3.14.7 | 1000 | 19.31 | 11.64 |
| 3.14.7 | 10000 | 223.82 | 11.55 |

## Collection iteration

| Python | Size | Plain list | Protected view |
| --- | ---: | ---: | ---: |
| 3.9.25 | 100 | 1.92 | 595.49 |
| 3.9.25 | 1000 | 19.68 | 5527.41 |
| 3.9.25 | 10000 | 182.18 | 54723.93 |
| 3.10.21 | 100 | 1.92 | 557.04 |
| 3.10.21 | 1000 | 17.73 | 5423.60 |
| 3.10.21 | 10000 | 170.95 | 55401.21 |
| 3.11.16 | 100 | 1.53 | 383.53 |
| 3.11.16 | 1000 | 15.29 | 3910.48 |
| 3.11.16 | 10000 | 118.38 | 38527.68 |
| 3.12.2 | 100 | 1.51 | 339.00 |
| 3.12.2 | 1000 | 11.94 | 3355.60 |
| 3.12.2 | 10000 | 118.40 | 34012.69 |
| 3.13.15 | 100 | 1.21 | 303.18 |
| 3.13.15 | 1000 | 11.74 | 3072.95 |
| 3.13.15 | 10000 | 124.33 | 30757.73 |
| 3.14.7 | 100 | 1.40 | 334.12 |
| 3.14.7 | 1000 | 14.11 | 3344.25 |
| 3.14.7 | 10000 | 143.63 | 33316.40 |

## One changed graph leaf

| Python | Size | Fresh graph | Incremental graph |
| --- | ---: | ---: | ---: |
| 3.9.25 | 100 | 64.27 | 311.63 |
| 3.9.25 | 1000 | 686.78 | 302.87 |
| 3.9.25 | 10000 | 6919.85 | 497.22 |
| 3.10.21 | 100 | 63.80 | 275.03 |
| 3.10.21 | 1000 | 671.56 | 295.56 |
| 3.10.21 | 10000 | 6612.45 | 486.90 |
| 3.11.16 | 100 | 48.74 | 205.61 |
| 3.11.16 | 1000 | 585.63 | 225.63 |
| 3.11.16 | 10000 | 5230.55 | 382.44 |
| 3.12.2 | 100 | 38.78 | 184.86 |
| 3.12.2 | 1000 | 458.29 | 198.30 |
| 3.12.2 | 10000 | 5273.20 | 338.78 |
| 3.13.15 | 100 | 37.11 | 165.50 |
| 3.13.15 | 1000 | 477.09 | 179.95 |
| 3.13.15 | 10000 | 5144.25 | 325.89 |
| 3.14.7 | 100 | 47.45 | 195.75 |
| 3.14.7 | 1000 | 658.78 | 215.74 |
| 3.14.7 | 10000 | 7192.51 | 419.33 |

## Raw measurements

- [CPython 3.9.25](results/cpython-39.json)
- [CPython 3.10.21](results/cpython-310.json)
- [CPython 3.11.16](results/cpython-311.json)
- [CPython 3.12.2](results/cpython-312.json)
- [CPython 3.13.15](results/cpython-313.json)
- [CPython 3.14.7](results/cpython-314.json)

See [running the benchmarks](README.md) for commands and scenario definitions.
