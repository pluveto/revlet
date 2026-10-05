"""Render benchmark JSON files as a Markdown report using only the standard library."""

import argparse
import json
import os
import statistics
from pathlib import Path

SCENARIOS = (
    "fresh",
    "hit",
    "recompute",
    "cutoff_fresh",
    "cutoff",
    "unrelated",
    "update_and_read",
    "list_scan",
    "view_scan",
    "dag_fresh",
    "dag_sparse",
)


def load_report(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["schema_version"] != 1:
        raise ValueError("Unsupported benchmark format: " + str(path))
    parameters = report["parameters"]
    expected = {(size, name) for size in parameters["sizes"] for name in SCENARIOS}
    results = report["results"]
    actual = {(row["size"], row["scenario"]) for row in results}
    if actual != expected or len(actual) != len(results):
        raise ValueError("Incomplete or duplicate scenarios: " + str(path))
    for row in results:
        samples = row["samples_ns"]
        if len(samples) != parameters["iterations"] or any(
            type(value) is not int or value <= 0 for value in samples
        ):
            raise ValueError("Invalid sample data: " + str(path))
        if row["median_us"] != statistics.median(samples) / 1000:
            raise ValueError("Summary differs from raw samples: " + str(path))
    return report


def render(reports: list, paths: list, output: Path) -> str:
    first = reports[0]
    for report in reports[1:]:
        for key in ("parameters", "benchmark_sha256", "runtime_sha256"):
            if report[key] != first[key]:
                raise ValueError(
                    "Reports differ in " + key + "; measure the same workload and code."
                )
        for key in (
            "platform",
            "processor",
            "logical_cpus",
            "gc_enabled",
            "implementation",
            "revlet",
        ):
            if report["environment"][key] != first["environment"][key]:
                raise ValueError("Reports differ in " + key + "; compare the same environment.")
    parameters = first["parameters"]
    environment = first["environment"]
    reference = next((r for r in reports if r["environment"]["python"].startswith("3.12.")), first)
    size = max(parameters["sizes"])
    reference_rows = {
        row["scenario"]: row["median_us"] for row in reference["results"] if row["size"] == size
    }
    versions = ", ".join(r["environment"]["python"] for r in reports)
    dates = sorted({r["started_at"].split("T")[0] for r in reports})
    lines = [
        "# Benchmark results",
        "",
        "Measured with Revlet " + environment["revlet"] + " on " + ", ".join(dates) + " (UTC).",
        "All scenarios verified their results on every sample. Cached scenarios also",
        "verified query execution counts. The JSON files linked below contain every",
        "timing sample and the hashes of the benchmark and runtime source files.",
        "",
        "## Environment and method",
        "",
        "- Processor: " + environment["processor"] + ".",
        "- Platform: " + environment["platform"] + ".",
        "- Logical CPUs reported by the OS: " + str(environment["logical_cpus"]) + ".",
        "- " + environment["implementation"] + " versions: " + versions + ".",
        "- Samples per scenario and size: " + str(parameters["iterations"]) + ".",
        "- Untimed warmup calls: " + str(parameters["warmups"]) + ".",
        "- Graph fanout: " + str(parameters["fanout"]) + " independently cached leaf queries.",
        "- Garbage collection: " + ("enabled." if environment["gc_enabled"] else "disabled."),
        "",
        "Interpreters ran sequentially on the same host. Tables show median microseconds",
        "per call. Setup, input updates, checksums, and execution-count checks are outside",
        "the timed section, except that **update + read** includes the managed input write.",
        "The JSON summaries also include p95 and minimum latency.",
        "",
        "## Reading the results",
        "",
        "For Python {} at size {:,}:".format(reference["environment"]["python"], size),
        "",
        "- A warm cache hit takes {:.2f} µs, compared with {:.2f} µs for fresh calculation.".format(
            reference_rows["hit"], reference_rows["fresh"]
        ),
        "- An affected input update plus its query takes {:.2f} µs.".format(
            reference_rows["update_and_read"]
        ),
        "- When the intermediate result stays equal, validation takes {:.2f} µs versus"
        " {:.2f} µs for fresh calculation of the same result.".format(
            reference_rows["cutoff"], reference_rows["cutoff_fresh"]
        ),
        "- Updating one leaf of the graph takes {:.2f} µs versus {:.2f} µs to recompute"
        " all leaves (fresh/incremental ratio: {:.2f}).".format(
            reference_rows["dag_sparse"],
            reference_rows["dag_fresh"],
            reference_rows["dag_fresh"] / reference_rows["dag_sparse"],
        ),
        "- Protected collection iteration takes {:.2f} µs versus {:.2f} µs for a plain"
        " list ({:.2f} times the cost).".format(
            reference_rows["view_scan"],
            reference_rows["list_scan"],
            reference_rows["view_scan"] / reference_rows["list_scan"],
        ),
        "",
        "Small calculations can cost less than cache lookup and validation. Protected",
        "collection access adds a check per element. The tables make both costs visible",
        "alongside the work saved by reusing expensive queries. These measurements cover",
        "single-threaded scalar and collection workloads on the host above; they do not",
        "measure lock contention, native-array adapters, or application memory usage.",
    ]
    sections = [
        (
            "Scalar queries",
            [
                ("fresh", "Fresh"),
                ("hit", "Hit"),
                ("recompute", "Recompute"),
                ("unrelated", "Unrelated update"),
                ("update_and_read", "Update + read"),
            ],
        ),
        ("Equal-result cutoff", [("cutoff_fresh", "Fresh"), ("cutoff", "Incremental")]),
        ("Collection iteration", [("list_scan", "Plain list"), ("view_scan", "Protected view")]),
        (
            "One changed graph leaf",
            [("dag_fresh", "Fresh graph"), ("dag_sparse", "Incremental graph")],
        ),
    ]
    for heading, columns in sections:
        lines.extend(
            [
                "",
                "## " + heading,
                "",
                "| Python | Size | " + " | ".join(label for _, label in columns) + " |",
                "| --- | ---: | " + " | ".join("---:" for _ in columns) + " |",
            ]
        )
        for report in reports:
            results = {(r["size"], r["scenario"]): r for r in report["results"]}
            for size in parameters["sizes"]:
                cells = [report["environment"]["python"], str(size)]
                cells.extend("{:.2f}".format(results[size, key]["median_us"]) for key, _ in columns)
                lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "## Raw measurements", ""])
    for report, path in zip(reports, paths):
        relative = Path(os.path.relpath(path.resolve(), output.parent.resolve())).as_posix()
        lines.append("- [CPython {}]({})".format(report["environment"]["python"], relative))
    lines.extend(
        ["", "See [running the benchmarks](README.md) for commands and scenario definitions.", ""]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/RESULTS.md"))
    args = parser.parse_args()
    try:
        pairs = [(load_report(path), path) for path in args.results]
        pairs.sort(
            key=lambda pair: tuple(int(n) for n in pair[0]["environment"]["python"].split("."))
        )
        reports, paths = zip(*pairs)
        versions = [r["environment"]["python"] for r in reports]
        if len(versions) != len(set(versions)):
            raise ValueError("Duplicate Python versions in the input reports.")
        content = render(reports, paths, args.output)
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print("Wrote " + str(args.output))


if __name__ == "__main__":
    main()
