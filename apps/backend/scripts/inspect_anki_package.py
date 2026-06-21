"""Inspect an Anki package for recoverable scheduling and FSRS state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from moku_backend.services.anki_package_reader import (  # noqa: E402
    AnkiPackageError,
    inspect_anki_package,
)

DEFAULT_PACKAGE = r"D:\Downloads\Chinese 101__Chinese vocab.apkg"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "package_path",
        nargs="?",
        default=DEFAULT_PACKAGE,
        help=f"Path to .apkg/.colpkg. Defaults to {DEFAULT_PACKAGE!r}.",
    )
    args = parser.parse_args()

    try:
        summary = inspect_anki_package(args.package_path)
    except AnkiPackageError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
