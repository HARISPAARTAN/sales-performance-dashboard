"""Page weight of the replica (spec section 9, umbrella section 12).

Every file under web/ counts, so the total is an upper bound of what the page loads from its own origin: at most
3 MB (3,000,000 bytes) in total, at most 1.3 MB (1,300,000 bytes) for web/assets/data/replica.json.

Usage (from the repository root):
    uv run python tools/check_page_weight.py [--web web]
Exit codes: 0 within the budget, 1 over it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOTAL_LIMIT = 3_000_000
REPLICA_LIMIT = 1_300_000
REPLICA = Path("assets") / "data" / "replica.json"


def weights(web: Path) -> dict[str, int]:
    """Bytes per top-level entry of web/ (a folder counts with everything below it)."""
    out: dict[str, int] = {}
    for path in sorted(p for p in web.rglob("*") if p.is_file()):
        top = path.relative_to(web).parts[0]
        out[top] = out.get(top, 0) + path.stat().st_size
    return out


def problems(web: Path) -> list[str]:
    total = sum(weights(web).values())
    replica = (web / REPLICA).stat().st_size if (web / REPLICA).is_file() else 0
    found = []
    if total > TOTAL_LIMIT:
        found.append(f"web/ holds {total:,} bytes, more than {TOTAL_LIMIT:,}")
    if replica > REPLICA_LIMIT:
        found.append(f"replica.json holds {replica:,} bytes, more than {REPLICA_LIMIT:,}")
    if not replica:
        found.append("replica.json is missing")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the page weight of the replica.")
    parser.add_argument("--web", type=Path, default=ROOT / "web")
    args = parser.parse_args(argv)
    web = args.web.resolve()
    sizes = weights(web)
    for name, size in sizes.items():
        print(f"{name:<14} {size:>11,} bytes")
    total = sum(sizes.values())
    replica = (web / REPLICA).stat().st_size if (web / REPLICA).is_file() else 0
    print(f"{'total':<14} {total:>11,} bytes of {TOTAL_LIMIT:,} ({100 * total / TOTAL_LIMIT:.0f} %)")
    print(f"{'replica.json':<14} {replica:>11,} bytes of {REPLICA_LIMIT:,} ({100 * replica / REPLICA_LIMIT:.0f} %)")
    found = problems(web)
    for problem in found:
        print(f"FAIL {problem}")
    if not found:
        print("page weight ok")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
