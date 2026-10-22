"""Static checks that pyproject.toml, CI and the contributor docs agree on what is verified.

The first version of this drift: `mypy --strict src/variance_agent scripts` was green in CI while
`deterministic_conditioning` carried five strict errors. mypy only follows imports into an
editable-installed package silently, so whether the errors showed depended on the checkout path.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("src/variance_agent", "scripts", "deterministic_conditioning")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_mypy_files_list_every_python_package() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert set(PACKAGES) <= set(config["tool"]["mypy"]["files"])


def test_ci_runs_mypy_and_compileall_over_every_package() -> None:
    mypy = re.search(r"python -m mypy --strict (.+)", CI)
    compileall = re.search(r"python -m compileall -q (.+)", CI)
    assert mypy is not None and compileall is not None
    for package in PACKAGES:
        assert package in mypy.group(1).split(), "CI mypy skips " + package
    assert "deterministic_conditioning" in compileall.group(1).split()


def test_contributor_docs_use_the_ci_commands() -> None:
    for name in ("README.md", "CONTRIBUTING.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "mypy --strict src/variance_agent scripts deterministic_conditioning" in text, name
        assert "compileall -q src tests scripts deterministic_conditioning" in text, name
        install = re.search(r"pip install -c requirements-typecheck\.txt -e '\.\[([^\]]+)\]'", text)
        assert install is not None, name
        assert {"dev", "excel", "pdf"} <= set(install.group(1).split(",")), name
