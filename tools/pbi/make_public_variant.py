"""Build the public variant of the Power BI project: the same model and report without row-level security.

    uv run python tools/pbi/make_public_variant.py [SRC_PBIP] [OUT_DIR]

Defaults: the PBIP named in tools/pbi/project.json to build/public/. The copy is renamed with the suffix of
`public_variant` (.pbip, .SemanticModel, .Report), the paths inside the .pbip and definition.pbir follow the rename,
definition/roles/ and the `ref role` lines in model.tmdl are removed, so are the tables in `drop_tables` (their
file, their `ref table` line and their query-order entry; they must have no relationships), and OUT_DIR/README.txt
says what the copy is for. Every other file is copied byte for byte. Desktop's local files (.pbi/) are not copied.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROJECT = json.loads((HERE / "project.json").read_text(encoding="utf-8"))
VARIANT = PROJECT["public_variant"]
SUFFIX = VARIANT["suffix"]
ORDER = "annotation PBI_QueryOrder = "


def _quoted(name: str) -> str:
    """A TMDL object name as written in a `ref` line."""
    return f"'{name}'" if any(ch in name for ch in " .=:'\t%") else name


def _rewrite(path: Path, replacements: dict[str, str]) -> None:
    text = path.read_bytes().decode("utf-8")
    for old, new in replacements.items():
        if old not in text:
            raise ValueError(f"{path.name}: expected to find {old!r}")
        text = text.replace(old, new)
    path.write_bytes(text.encode("utf-8"))


def _drop_lines(path: Path, tables: list[str]) -> None:
    """model.tmdl without the `ref role` lines, the `ref table` lines of `tables` and their entries in the query
    order annotation."""
    drop = {f"ref table {_quoted(t)}" for t in tables}
    out = []
    for line in path.read_bytes().decode("utf-8").splitlines(keepends=True):
        if line.lstrip().startswith("ref role") or line.strip() in drop:
            continue
        if line.startswith(ORDER):
            order = [name for name in json.loads(line[len(ORDER) :]) if name not in tables]
            line = ORDER + json.dumps(order, separators=(",", ":")) + "\n"
        out.append(line)
    path.write_bytes("".join(out).encode("utf-8"))


def build(src_pbip: Path, out_dir: Path) -> Path:
    """Copy the PBIP under the renamed names into out_dir (created if needed) and return the new .pbip path."""
    src_pbip, out_dir = Path(src_pbip), Path(out_dir)
    base = src_pbip.stem
    new = base + SUFFIX
    src_model, src_report = src_pbip.parent / f"{base}.SemanticModel", src_pbip.parent / f"{base}.Report"
    if not (src_pbip.is_file() and src_model.is_dir() and src_report.is_dir()):
        raise FileNotFoundError(f"{src_pbip}, {src_model} and {src_report} must all exist")

    out_dir.mkdir(parents=True, exist_ok=True)
    dst_pbip = out_dir / f"{new}.pbip"
    dst_model, dst_report = out_dir / f"{new}.SemanticModel", out_dir / f"{new}.Report"
    for old in (dst_pbip, dst_model, dst_report, out_dir / "README.txt"):  # only our own previous output
        if old.is_dir():
            shutil.rmtree(old)
        elif old.exists():
            old.unlink()

    ignore = shutil.ignore_patterns(".pbi")
    shutil.copytree(src_model, dst_model, ignore=ignore)
    shutil.copytree(src_report, dst_report, ignore=ignore)
    shutil.copyfile(src_pbip, dst_pbip)

    _rewrite(dst_pbip, {f"{base}.Report": f"{new}.Report"})
    _rewrite(dst_report / "definition.pbir", {f"{base}.SemanticModel": f"{new}.SemanticModel"})
    definition = dst_model / "definition"
    shutil.rmtree(definition / "roles", ignore_errors=True)
    relationships = (definition / "relationships.tmdl").read_text(encoding="utf-8")
    for table in VARIANT["drop_tables"]:
        if f"{_quoted(table)}." in relationships:
            raise ValueError(f"{table} has a relationship; the public variant cannot drop it")
        (definition / "tables" / f"{table}.tmdl").unlink()
    _drop_lines(definition / "model.tmdl", VARIANT["drop_tables"])
    (out_dir / "README.txt").write_text("\n".join(VARIANT["readme"]) + "\n", encoding="utf-8", newline="\n")
    return dst_pbip


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    src = Path(args[0]) if args else ROOT / PROJECT["folder"] / f"{PROJECT['name']}.pbip"
    out = Path(args[1]) if len(args) > 1 else ROOT / "build" / "public"
    dst = build(src, out)
    print(dst.relative_to(ROOT).as_posix() if dst.is_relative_to(ROOT) else dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
