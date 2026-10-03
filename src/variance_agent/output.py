"""Stage text outputs before atomically replacing each destination file."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Mapping


def write_text_outputs(outputs: Mapping[Path, str]) -> None:
    targets = [(Path(path).resolve(), text) for path, text in outputs.items()]
    paths = [path for path, _ in targets]
    for index, path in enumerate(paths):
        if path.exists() and not path.is_file():
            raise ValueError(f"Output destination is not a regular file: {path}")
        for other in paths[:index]:
            if (
                path == other
                or path in other.parents
                or other in path.parents
                or (path.exists() and other.exists() and path.samefile(other))
            ):
                raise ValueError("Output paths must be distinct and cannot contain one another.")

    staged: list[tuple[Path, Path]] = []
    try:
        for path, text in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                staged.append((temporary, path))
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists():
                temporary.chmod(path.stat().st_mode & 0o777)
        # Each replace is atomic; multiple replaces are not a filesystem transaction.
        for temporary, path in staged:
            os.replace(temporary, path)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
