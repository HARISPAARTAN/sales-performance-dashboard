"""Write the model diagram of the project (<name>.SemanticModel/diagramLayout.json).

    uv run python tools/pbi/diagram_layout.py

The rows come from `diagram` in tools/pbi/project.json: dimensions in the top row, facts below them, the tables
without relationships (measures, calculation group, field parameter, security) in a third row, so every relationship
line runs in the gap between the first two rows and none crosses a table. Desktop rewrites the file when it saves the
project; from then on the layout is kept in Desktop.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = json.loads((HERE / "project.json").read_text(encoding="utf-8"))
MODEL = HERE.parents[1] / PROJECT["folder"] / f"{PROJECT['name']}.SemanticModel"
WIDTH, HEIGHT, GAP_X, GAP_Y = 234, 280, 60, 150  # node size and gaps in diagram units


def layout(model: Path = MODEL, rows: list[list[str]] | None = None) -> dict:
    rows = PROJECT["diagram"] if rows is None else rows
    tables = {p.stem for p in (model / "definition" / "tables").glob("*.tmdl")}
    placed = [name for row in rows for name in row]
    if sorted(placed) != sorted(tables):
        raise ValueError(f"the rows must place every table once: {sorted(set(placed) ^ tables)}")
    widest = max(len(row) for row in rows) * (WIDTH + GAP_X) - GAP_X
    nodes = []
    for i, row in enumerate(rows):
        left = (widest - (len(row) * (WIDTH + GAP_X) - GAP_X)) / 2  # rows centred under each other
        for j, name in enumerate(row):
            tmdl = (model / "definition" / "tables" / f"{name}.tmdl").read_text(encoding="utf-8")
            nodes.append(
                {
                    "location": {"x": left + j * (WIDTH + GAP_X), "y": i * (HEIGHT + GAP_Y)},
                    "nodeIndex": name,
                    "nodeLineageTag": re.search(r"^\tlineageTag: (\S+)", tmdl, re.M).group(1),
                    "size": {"height": HEIGHT, "width": WIDTH},
                    "zIndex": len(nodes),
                }
            )
    diagram = {
        "ordinal": 0,
        "scrollPosition": {"x": 0, "y": 0},
        "nodes": nodes,
        "name": "All tables",
        "zoomValue": 70,
        "pinKeyFieldsToTop": False,
        "showExtraHeaderInfo": False,
        "hideKeyFieldsWhenCollapsed": False,
        "tablesLocked": False,
    }
    return {"version": "1.1.0", "diagrams": [diagram], "selectedDiagram": "All tables", "defaultDiagram": "All tables"}


def main() -> None:
    path = MODEL / "diagramLayout.json"
    path.write_text(json.dumps(layout(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(HERE.parents[1]).as_posix()}")


if __name__ == "__main__":
    main()
