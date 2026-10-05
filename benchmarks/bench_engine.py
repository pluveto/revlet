"""Measure exact-result incremental workloads on Python 3.9+.

Run from the repository root:
    python benchmarks/bench_engine.py --json benchmarks/results/local.json
"""

import argparse
import gc
import hashlib
import json
import math
import os
import platform
import statistics
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import Optional

import revlet
from revlet import Database, tracked


def noop() -> None:
    pass


@dataclass
class Scenario:
    name: str
    operation: Callable[[], int]
    prepare: Callable[[], None]
    expected: Callable[[], int]
    database: Optional[Database] = None
    executions_per_sample: int = 0


def work(size: int, value: int) -> int:
    total = 0
    for _ in range(size):
        total += value
    return total


def scan(values: Iterable[int]) -> int:
    total = 0
    for value in values:
        total += value
    return total


def scalar_scenario(name: str, size: int) -> Scenario:
    state = [3]

    def advance_plain() -> None:
        state[0] = 8 - state[0]  # Alternate 3 and 5, both odd.

    if name in ("fresh", "cutoff_fresh"):

        def current() -> int:
            return state[0] % 2 if name == "cutoff_fresh" else state[0]

        return Scenario(
            name, lambda: work(size, current()), advance_plain, lambda: size * current()
        )

    db = Database()
    source = db.input(state[0])
    unrelated = db.input(0)
    cutoff = name == "cutoff"

    @tracked
    def stage(value):
        current = value.value
        return current % 2 if cutoff else current

    @tracked
    def calculate(value):
        return work(size, stage(value))

    def query() -> int:
        return calculate(source)

    def advance() -> None:
        if name == "unrelated":
            unrelated.value = 1 - unrelated.value
        else:
            advance_plain()
            source.value = state[0]

    def expected() -> int:
        return size * (state[0] % 2 if cutoff else state[0])

    if query() != expected():
        raise RuntimeError("Scalar scenario initialization failed.")

    prepare = noop if name == "hit" else advance
    operation = query
    executions = 0 if name in ("hit", "unrelated") else (1 if cutoff else 2)
    if name == "update_and_read":
        prepare = noop

        def operation() -> int:
            advance()
            return query()

    return Scenario(name, operation, prepare, expected, db, executions)


def iteration_scenario(size: int, guarded: bool) -> Scenario:
    values = list(range(size))
    db = Database() if guarded else None
    view = db.input(values).value if db is not None else values
    return Scenario(
        "view_scan" if guarded else "list_scan",
        lambda: scan(view),
        noop,
        lambda: size * (size - 1) // 2,
        db,
    )


def graph_scenario(size: int, fanout: int, cached: bool) -> Scenario:
    values = list(range(1, fanout + 1))
    cursor = [0]
    db = Database() if cached else None
    inputs = [db.input(value) for value in values] if db is not None else []

    @tracked
    def leaf(value):
        return work(size, value.value)

    @tracked
    def total():
        return sum(leaf(value) for value in inputs)

    def fresh() -> int:
        return sum(work(size, value) for value in values)

    query = db.bind(total) if db is not None else fresh

    def expected() -> int:
        return size * sum(values)

    def prepare() -> None:
        index = cursor[0] % fanout
        cursor[0] += 1
        values[index] += 1
        if db is not None:
            inputs[index].value = values[index]

    if query() != expected():
        raise RuntimeError("Graph scenario initialization failed.")
    return Scenario("dag_sparse" if cached else "dag_fresh", query, prepare, expected, db, 2)


def measure(scenario: Scenario, iterations: int, warmups: int) -> dict:
    def check(result: int) -> None:
        expected = scenario.expected()
        if type(result) is not int or result != expected:
            raise RuntimeError(f"{scenario.name}: got {result}, expected {expected}.")

    try:
        gc.collect()
        for _ in range(warmups):
            scenario.prepare()
            check(scenario.operation())
        db = scenario.database
        before = db.cache_info().executions if db is not None else 0
        samples = []
        for _ in range(iterations):
            scenario.prepare()
            start = time.perf_counter_ns()
            result = scenario.operation()
            elapsed = time.perf_counter_ns() - start
            check(result)
            samples.append(elapsed)
        executions = db.cache_info().executions - before if db is not None else None
        if db is not None and executions != iterations * scenario.executions_per_sample:
            raise RuntimeError(f"{scenario.name}: unexpected query execution count {executions}.")
        ordered = sorted(samples)
        return {
            "scenario": scenario.name,
            "samples_ns": samples,
            "median_us": statistics.median(samples) / 1000,
            "p95_us": ordered[math.ceil(0.95 * len(ordered)) - 1] / 1000,
            "min_us": min(samples) / 1000,
            "query_executions": executions,
        }
    finally:
        if scenario.database is not None:
            scenario.database.close()


def processor_name() -> str:
    name = platform.processor()
    if name:
        return name
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.machine()


def runtime_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(revlet.__file__).parent.glob("*.py")):
        digest.update(path.name.encode("utf-8") + b"\0" + path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", "--size", nargs="+", type=int, default=[100, 1000, 10000])
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--warmups", type=int, default=20)
    parser.add_argument("--fanout", type=int, default=32)
    parser.add_argument(
        "--json", type=Path, help="Save environment, statistics, and all raw samples."
    )
    args = parser.parse_args()
    if min([*args.sizes, args.iterations, args.fanout]) < 1 or args.warmups < 0:
        parser.error("sizes, iterations, and fanout must be positive; warmups must be non-negative")
    if len(args.sizes) != len(set(args.sizes)):
        parser.error("sizes must be unique")
    report = {
        "schema_version": 1,
        "environment": {
            "revlet": version("revlet"),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "processor": processor_name(),
            "logical_cpus": os.cpu_count(),
            "gc_enabled": gc.isenabled(),
        },
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime_sha256": runtime_digest(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "sizes": args.sizes,
            "iterations": args.iterations,
            "warmups": args.warmups,
            "fanout": args.fanout,
        },
        "results": [],
    }
    print(
        "revlet {} / {} {}".format(
            report["environment"]["revlet"],
            platform.python_implementation(),
            platform.python_version(),
        ),
        flush=True,
    )
    print("size     scenario           median (us)     p95 (us)", flush=True)
    for size in args.sizes:
        factories = [
            partial(scalar_scenario, name, size)
            for name in (
                "fresh",
                "hit",
                "recompute",
                "cutoff_fresh",
                "cutoff",
                "unrelated",
                "update_and_read",
            )
        ]
        factories.extend(
            [
                partial(iteration_scenario, size, False),
                partial(iteration_scenario, size, True),
                partial(graph_scenario, size, args.fanout, False),
                partial(graph_scenario, size, args.fanout, True),
            ]
        )
        for factory in factories:
            result = measure(factory(), args.iterations, args.warmups)
            result["size"] = size
            report["results"].append(result)
            print(
                "{:<8} {:<18} {:>11.2f} {:>12.2f}".format(
                    size, result["scenario"], result["median_us"], result["p95_us"]
                ),
                flush=True,
            )
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {args.json}", flush=True)


if __name__ == "__main__":
    main()
