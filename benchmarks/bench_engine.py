"""Local timings for recomputation, hits, cutoff, and guarded iteration.

Writes happen outside the timed section. Median is over ``--iterations`` samples.
The cutoff case changes a scalar inside one comparison bucket, so the heavy
consumer validates instead of running its loop again.

    python benchmarks/bench_engine.py --iterations 2000 --size 10000
"""

import argparse
import platform
import statistics
import sys
import time
from typing import Callable

from revlet import Database, tracked

BUCKET = 1_000_000


def measure(operation: Callable[[], object], iterations: int) -> float:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - start) * 1e6)
    return float(statistics.median(samples))


def direct_loop(size: int, base: int) -> int:
    total = 0
    for _ in range(size):
        total += base
    return total


def same_bucket(old: int, new: int) -> bool:
    return old // BUCKET == new // BUCKET


def build_heavy(size: int, equivalent: bool):
    db = Database()
    source = db.input(0)
    step = {"n": 0}

    @tracked
    def raw(value):
        return value.value

    if equivalent:

        @tracked(equivalent=same_bucket)
        def stage(value):
            return raw(value)

    else:

        @tracked
        def stage(value):
            return raw(value)

    @tracked
    def heavy(value):
        base = stage(value)
        total = 0
        for _ in range(size):
            total += base
        return total

    heavy(source)

    def advance():
        step["n"] += 1
        if equivalent and step["n"] >= BUCKET:
            raise RuntimeError("cutoff samples left the comparison bucket")
        source.value = step["n"]

    return advance, lambda: heavy(source)


def guarded_iteration(size: int) -> Callable[[], int]:
    db = Database()
    view = db.input(list(range(size))).value

    def scan() -> int:
        total = 0
        for value in view:
            total += value
        return total

    return scan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--size", type=int, default=10000)
    args = parser.parse_args()
    if args.iterations < 1 or args.size < 1:
        raise SystemExit("--iterations and --size must be positive")

    advance_raw, heavy_raw = build_heavy(args.size, equivalent=False)
    advance_cutoff, heavy_cutoff = build_heavy(args.size, equivalent=True)
    scan = guarded_iteration(args.size)
    base = 3
    if direct_loop(args.size, base) != args.size * base:
        raise SystemExit("direct loop failed its checksum")
    advance_raw()
    if heavy_raw() != args.size:
        raise SystemExit("changed-scalar query failed its checksum")
    advance_cutoff()
    if heavy_cutoff() != 0:
        raise SystemExit("cutoff query recomputed the heavy result")
    if scan() != sum(range(args.size)):
        raise SystemExit("guarded iteration failed its checksum")

    print("revlet bench_engine")
    print(f"python: {platform.python_implementation()} {sys.version.split()[0]}")
    print(f"platform: {platform.platform()}")
    print(f"processor: {platform.processor() or 'unknown'}")
    print(f"size: {args.size} loop steps or container elements")
    print(f"iterations: {args.iterations} timed samples; median; writes excluded")
    print("update: scalar input increases by 1; cutoff stays in the initial bucket")
    direct = measure(lambda: direct_loop(args.size, base), args.iterations)
    hit = measure(heavy_raw, args.iterations)
    changed = measure_after(advance_raw, heavy_raw, args.iterations)
    cutoff = measure_after(advance_cutoff, heavy_cutoff, args.iterations)
    guarded = measure(scan, args.iterations)
    print(f"{'direct recompute':<22} {direct:10.1f} us")
    print(f"{'warm cache hit':<22} {hit:10.1f} us")
    print(f"{'changed scalar':<22} {changed:10.1f} us")
    print(f"{'output cutoff':<22} {cutoff:10.1f} us")
    print(f"{'guarded iteration':<22} {guarded:10.1f} us")


def measure_after(
    prepare: Callable[[], None], operation: Callable[[], object], iterations: int
) -> float:
    samples = []
    for _ in range(iterations):
        prepare()
        start = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - start) * 1e6)
    return float(statistics.median(samples))


if __name__ == "__main__":
    main()
