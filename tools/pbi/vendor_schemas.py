"""Vendor the pinned PBIP/PBIR JSON schemas (microsoft/json-schemas, MIT) into tools/pbi/schemas/, offline.

    uv run python tools/pbi/vendor_schemas.py --from <folder>          # copy, then trim
    uv run python tools/pbi/vendor_schemas.py --from <folder> --check  # exit 1 if tools/pbi/schemas differs

<folder> holds the files below at their upstream paths: a checkout of microsoft/json-schemas at COMMIT, or the
tools/pbi/schemas folder of another repository that vendored the same commit. Nothing is downloaded.

Trimming: the schemas list one product name among the sources of a page or visual (`howCreated`) and as a visual
header button. The repository names no such product, so `trim` drops those two kinds of entries, found by shape (an
enum entry whose description reads "... created by <name>." and a header property `show<Name>SummaryButton`), never
by the name itself. Nothing else changes; the report files never use either entry. Untouched files are copied byte
for byte; trimmed ones are written as upstream formats them (four-space indent, no final newline).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

COMMIT = "5e1199a15b80e3d51198fe017b1a6fb9bb0871a6"  # microsoft/json-schemas main, 2026-10-23
OUT = Path(__file__).parent / "schemas"
FILES = [
    "LICENSE",
    "fabric/pbip/pbipProperties/1.0.0/schema.json",
    "fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
    "fabric/item/report/definitionProperties/2.0.0/schema.json",
    "fabric/item/report/definition/report/3.3.0/schema.json",
    "fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
    "fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
    "fabric/item/report/definition/page/2.1.0/schema.json",
    "fabric/item/report/definition/visualContainer/2.13.0/schema.json",
    "fabric/item/report/definition/bookmark/2.1.0/schema.json",
    "fabric/item/report/definition/bookmarksMetadata/1.0.0/schema.json",
    "fabric/item/report/definition/visualConfiguration/2.8.0/schema.json",
    "fabric/item/report/definition/visualConfiguration/2.8.0/schema-embedded.json",
    "fabric/item/report/definition/filterConfiguration/1.3.0/schema.json",
    "fabric/item/report/definition/filterConfiguration/1.3.0/schema-embedded.json",
    "fabric/item/report/definition/semanticQuery/1.4.0/schema.json",
    "fabric/item/report/definition/formattingObjectDefinitions/1.5.0/schema.json",
]
CREATED_BY = re.compile(r"(?i)\bcreated by [a-z]+\.$")
SUMMARY_BUTTON = re.compile(r"show[A-Z][a-z]+SummaryButton")


def trim(node) -> int:
    """Drop the product entries below `node` in place; return how many were dropped."""
    dropped = 0
    if isinstance(node, dict):
        for key in [k for k in node if SUMMARY_BUTTON.fullmatch(k)]:
            del node[key]
            dropped += 1
        options = node.get("anyOf")
        if isinstance(options, list):
            kept = [
                o
                for o in options
                if not (isinstance(o, dict) and "const" in o and CREATED_BY.search(o.get("description", "")))
            ]
            dropped += len(options) - len(kept)
            node["anyOf"] = kept
        for value in node.values():
            dropped += trim(value)
    elif isinstance(node, list):
        for value in node:
            dropped += trim(value)
    return dropped


def vendored(src: Path, rel: str) -> tuple[bytes, int]:
    """The bytes tools/pbi/schemas/<rel> must hold, and the number of entries trimmed from it."""
    raw = (src / rel).read_bytes()
    if not rel.endswith(".json"):
        return raw, 0
    data = json.loads(raw.decode("utf-8-sig"))
    dropped = trim(data)
    if not dropped:
        return raw, 0
    return json.dumps(data, indent=4, ensure_ascii=False).encode("utf-8"), dropped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vendor the pinned PBIR schemas from a local folder.")
    ap.add_argument("--from", dest="src", type=Path, required=True, help="folder with the upstream paths")
    ap.add_argument("--check", action="store_true", help="compare instead of writing")
    args = ap.parse_args(argv)
    differ, total = [], 0
    for rel in FILES:
        data, dropped = vendored(args.src, rel)
        total += dropped
        dest = OUT / rel
        if args.check:
            if not dest.is_file() or dest.read_bytes() != data:
                differ.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dropped:
            dest.write_bytes(data)
        else:
            shutil.copyfile(args.src / rel, dest)
        print(f"vendored {rel}" + (f" ({dropped} entr{'y' if dropped == 1 else 'ies'} trimmed)" if dropped else ""))
    if args.check:
        for rel in differ:
            print(f"FAIL tools/pbi/schemas/{rel} differs")
        if not differ:
            print(f"tools/pbi/schemas matches {len(FILES)} files ({total} entries trimmed)")
        return 1 if differ else 0
    print(f"{len(FILES)} files, {total} entries trimmed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
