"""Copy Microsoft's Tabular Object Model client (six assemblies) into build/tom/ for the optional TOM test.

    uv run python tools/pbi/copy_tom.py --from <folder with the six DLLs>

The assemblies come from the NuGet package microsoft.analysisservices.netcore.retail.amd64 19.84.1
(lib/netcoreapp3.0); any folder that already holds them works, for example the build/tom/ folder of another local
repository. Each file is checked against its SHA-256 before it is copied. Nothing is downloaded, and build/ is
git-ignored, so no assembly is committed. tests/pbi/test_tmdl_tom.py skips while build/tom/ is empty.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "build" / "tom"
PREFIX = "Microsoft.AnalysisServices"
DIGESTS = {  # file name after the prefix -> SHA-256
    ".Core.dll": "641ca518a2bb8eee43cc262dc85eeb521ba64faa72652f99d5eab718e38dba44",
    ".Runtime.Core.dll": "526098ada2d7a4d8e048ec7f978af10d49d914b6badab5c7054ef748758db907",
    ".Runtime.Windows.dll": "2580bfe465cd54b7c23a691379e8ce3d3a7a5bb735e3a6caf15fd67458586759",
    ".Tabular.Json.dll": "cd8e8f8037a111d449f9a4179d1e58ea6afa00b9099f81a89f67a9105e6851a3",
    ".Tabular.dll": "b450fa4ed088cb8bf72590958b4381c58fb811d00b8a4c8d38b8738d939d7229",
    ".dll": "b1e703fef41ea2233a0435954219133aaebde155b4b1ab4b35a6e02c1256b6fb",
}
FILES = {PREFIX + suffix: digest for suffix, digest in DIGESTS.items()}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Copy the TOM client assemblies into build/tom/.")
    ap.add_argument("--from", dest="src", type=Path, required=True)
    args = ap.parse_args(argv)
    bad = []
    for name, digest in FILES.items():
        path = args.src / name
        if not path.is_file():
            bad.append(f"{name}: missing in {args.src}")
        elif sha256(path) != digest:
            bad.append(f"{name}: SHA-256 {sha256(path)} is not {digest}")
    if bad:
        print("\n".join(f"FAIL {line}" for line in bad))
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(args.src / name, OUT / name)
    print(f"copied {len(FILES)} assemblies into build/tom")
    return 0


if __name__ == "__main__":
    sys.exit(main())
