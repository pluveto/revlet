"""Validate release metadata and the exact archives to be published (Python 3.12+)."""

import argparse
import ast
import hashlib
import sys
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_source(tag=None):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    require(project["name"] == "revlet", "The distribution name must be revlet.")
    require(project["requires-python"] == ">=3.9", "Review the supported Python versions.")
    require(project.get("dependencies", []) == [], "Unexpected runtime dependencies.")
    require(project.get("license"), "Select a license and set project.license before release.")
    require((ROOT / "LICENSE").is_file(), "The LICENSE file is missing.")
    require(project.get("license-files") == ["LICENSE"], "Declare LICENSE in license-files.")
    require(project.get("authors"), "Set the project authors before release.")
    urls = project.get("urls", {})
    for name in ("Source", "Issues", "Documentation", "Changelog"):
        require(urls.get(name, "").startswith("https://"), "Missing project URL: " + name)
    version = project["version"]
    if tag is not None:
        require(tag == "v" + version, "The selected tag must equal v" + version + ".")
        require(".dev" not in version, "Development versions cannot use the release workflow.")
    require(
        "## " + version + " " in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
        "Add a changelog entry for " + version + ".",
    )
    return project


def check_metadata(data, project):
    metadata = BytesParser().parsebytes(data)
    for header, key in (
        ("Name", "name"),
        ("Version", "version"),
        ("Requires-Python", "requires-python"),
        ("License-Expression", "license"),
    ):
        require(metadata[header] == project[key], "Incorrect metadata: " + header)
    require(not metadata.get_all("Requires-Dist"), "Unexpected runtime dependencies in archive.")
    require(metadata.get_all("License-File") == ["LICENSE"], "Missing license metadata.")
    require(metadata["Description-Content-Type"] == "text/markdown", "README is not Markdown.")
    require(
        metadata["Author"] == ", ".join(a["name"] for a in project["authors"]),
        "Author metadata does not match pyproject.toml.",
    )
    expected_urls = {name + ", " + url for name, url in project["urls"].items()}
    require(
        set(metadata.get_all("Project-URL", [])) == expected_urls,
        "Project URLs do not match pyproject.toml.",
    )


def check_archives(directory, project):
    version = project["version"]
    wheel_name = "revlet-" + version + "-py3-none-any.whl"
    sdist_name = "revlet-" + version + ".tar.gz"
    require(directory.is_dir(), "Build the distributions first.")
    require(
        {p.name for p in directory.iterdir()} == {wheel_name, sdist_name},
        "The distribution directory must contain only the expected wheel and sdist.",
    )
    source = ROOT / "src" / "revlet"
    package_files = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file() and (p.suffix in (".py", ".pyi") or p.name == "py.typed")
    }
    require("__init__.pyi" in package_files and "py.typed" in package_files, "Missing types.")
    with zipfile.ZipFile(directory / wheel_name) as wheel:
        names = wheel.namelist()
        require(len(names) == len(set(names)), "Duplicate wheel members.")
        info = "revlet-" + version + ".dist-info/"
        expected = {"revlet/" + name for name in package_files}
        expected.update(info + name for name in ("METADATA", "WHEEL", "RECORD", "licenses/LICENSE"))
        require(set(names) == expected, "Unexpected or missing files in wheel.")
        for name, data in package_files.items():
            require(wheel.read("revlet/" + name) == data, "Wheel source mismatch: " + name)
            if name.endswith(".py"):
                ast.parse(data, filename=name, feature_version=(3, 9))
        check_metadata(wheel.read(info + "METADATA"), project)
        wheel_metadata = BytesParser().parsebytes(wheel.read(info + "WHEEL"))
        require(wheel_metadata["Root-Is-Purelib"] == "true", "Expected a pure Python wheel.")
        require(wheel_metadata.get_all("Tag") == ["py3-none-any"], "Unexpected wheel tag.")
        require(
            wheel.read(info + "licenses/LICENSE") == (ROOT / "LICENSE").read_bytes(),
            "Wheel license mismatch.",
        )
    with tarfile.open(directory / sdist_name) as sdist:
        members = sdist.getmembers()
        names = [member.name for member in members]
        require(len(names) == len(set(names)), "Duplicate sdist members.")
        prefix = "revlet-" + version + "/"
        configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        included = configuration["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
        public_documents = {path.lstrip("/") for path in included if path.endswith(".md")}
        for member in members:
            require(member.name.startswith(prefix), "Unexpected sdist root.")
            require(".." not in member.name.split("/"), "Unsafe archive path.")
            require(member.isfile() or member.isdir(), "Links are not allowed in the sdist.")
            if member.isfile() and member.name.lower().endswith(".md"):
                require(
                    member.name[len(prefix) :] in public_documents,
                    "Unlisted documentation in sdist: " + member.name,
                )
        required = [
            "pyproject.toml",
            "uv.lock",
            "LICENSE",
            "README.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "docs/usage.md",
            "docs/implementation.md",
            "docs/compatibility.md",
            "scripts/check_dist.py",
            "tests/test_distribution.py",
            "examples/basic.py",
            "benchmarks/bench_engine.py",
            "benchmarks/report.py",
            "benchmarks/RESULTS.md",
            ".github/workflows/ci.yml",
        ]
        required.extend("src/revlet/" + name for name in package_files)
        required.extend(
            path.relative_to(ROOT).as_posix()
            for path in sorted((ROOT / "benchmarks/results").glob("cpython-*.json"))
        )
        for name in required:
            member = sdist.extractfile(prefix + name)
            require(member is not None, "Missing sdist file: " + name)
            require(member.read() == (ROOT / name).read_bytes(), "Sdist source mismatch: " + name)
        metadata = sdist.extractfile(prefix + "PKG-INFO")
        require(metadata is not None, "Missing sdist metadata.")
        check_metadata(metadata.read(), project)
    for name in (wheel_name, sdist_name):
        digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        print(digest + "  " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--tag", help="Require this release tag to match the project version.")
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    try:
        project = check_source(args.tag)
        if not args.source_only:
            check_archives(args.dist, project)
    except (
        ValueError,
        KeyError,
        OSError,
        tarfile.TarError,
        zipfile.BadZipFile,
        SyntaxError,
    ) as error:
        print("Release check failed: " + str(error), file=sys.stderr)
        return 1
    print("Release checks passed for revlet " + project["version"] + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
