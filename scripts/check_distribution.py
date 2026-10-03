"""Validate archive contents without extracting potentially unsafe archive paths."""

import argparse
from email.parser import BytesParser
from pathlib import Path
import tarfile
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    wheels = list(args.directory.glob("*.whl"))
    sources = list(args.directory.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "Expected one wheel and one sdist"
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        assert "variance_agent/version.py" in names
        assert any(name.endswith("/licenses/LICENSE") for name in names)
        metadata = BytesParser().parsebytes(wheel.read(next(
            name for name in names if name.endswith(".dist-info/METADATA"))))
        assert metadata["License-Expression"] == "MIT"
        assert metadata["Requires-Python"] == ">=3.11"
        entry = wheel.read(next(name for name in names if name.endswith("/entry_points.txt")))
        assert b"variance-agent = variance_agent.cli:main" in entry
    with tarfile.open(sources[0], "r:gz") as source:
        names = source.getnames()
        for required in ("LICENSE", "pyproject.toml", "src/variance_agent/version.py",
                         "schemas/audit-1.0.schema.json", "schemas/audit-1.3.schema.json",
                         "schemas/audit-1.4.schema.json",
                         "tests/fixtures/contracts/complete.report.md", "docs/audit-contract.md",
                         "scripts/check_installation.py"):
            assert any(name.endswith("/" + required) for name in names), required
    print("Wheel/sdist contents, license, Python support, and entry point verified")


if __name__ == "__main__":
    main()
