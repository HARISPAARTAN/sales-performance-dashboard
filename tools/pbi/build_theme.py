"""Write the report theme from the portfolio-kit tokens (dark set) named in tools/pbi/project.json.

    uv run python tools/pbi/build_theme.py            # write <Report>/StaticResources/RegisteredResources/<file>
    uv run python tools/pbi/build_theme.py --check    # exit 1 if the theme's content differs from a fresh build

Every colour of the theme is a kit token or a colour of the kit's categorical palette (--chart-1 to --chart-8), so
the report and the replica share one palette. Power BI cannot embed web fonts; the theme uses the fonts in
project.json (Segoe UI). With `"display_units": "none"` in the theme entry of project.json, data labels and value
axes of every visual show values without display units, as dynamic format strings need. Deterministic: sorted keys,
two-space indent, UTF-8 without BOM, LF. --check compares the parsed JSON, because Power BI Desktop rewrites the theme
file in its own layout when it saves the project.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROJECT = json.loads((HERE / "project.json").read_text(encoding="utf-8"))
TOKEN = re.compile(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\s*;")
NEEDED = ("bg", "surface", "surface-2", "border", "text", "muted", "accent", "ok", "warn", "danger", "info")


def theme_path() -> Path:
    report = ROOT / PROJECT["folder"] / f"{PROJECT['name']}.Report"
    return report / "StaticResources" / "RegisteredResources" / PROJECT["theme"]["file"]


def dark_tokens(css: str) -> dict[str, str]:
    """The hex tokens of the default (dark) block of tokens.css: everything before the light override."""
    dark = css.split(':root[data-theme="light"]', 1)[0]
    tokens = {name: value.upper() for name, value in TOKEN.findall(dark)}
    missing = [n for n in (*NEEDED, *(f"chart-{i}" for i in range(1, 9))) if n not in tokens]
    if missing:
        raise ValueError(f"tokens.css lacks {missing}")
    return tokens


def _solid(colour: str) -> dict:
    return {"solid": {"color": colour}}


def build(tokens: dict[str, str]) -> dict:
    t = tokens
    font, bold = PROJECT["theme"]["font"], PROJECT["theme"]["font_bold"]
    grid = [
        {
            "gridVertical": False,
            "gridHorizontal": True,
            "gridHorizontalColor": _solid(t["border"]),
            "outlineColor": _solid(t["border"]),
        }
    ]
    headers = [{"fontColor": _solid(t["muted"]), "backColor": _solid(t["surface"])}]
    total = [{"fontColor": _solid(t["text"]), "backColor": _solid(t["surface-2"])}]
    theme = {
        "name": PROJECT["theme"]["name"],
        "dataColors": [t[f"chart-{i}"] for i in range(1, 9)],
        "foreground": t["text"],
        "background": t["surface"],
        "firstLevelElements": t["text"],
        "secondLevelElements": t["muted"],
        "thirdLevelElements": t["border"],
        "fourthLevelElements": t["muted"],
        "secondaryBackground": t["surface-2"],
        "tableAccent": t["accent"],
        "hyperlink": t["accent"],
        "visitedHyperlink": t["accent"],
        "good": t["ok"],
        "neutral": t["warn"],
        "bad": t["danger"],
        "minimum": t["warn"],
        "center": t["surface"],
        "maximum": t["ok"],
        "textClasses": {
            "callout": {"fontSize": 24, "fontFace": bold, "color": t["text"]},
            "title": {"fontSize": 11, "fontFace": bold, "color": t["text"]},
            "header": {"fontSize": 12, "fontFace": bold, "color": t["text"]},
            "label": {"fontSize": 10, "fontFace": font, "color": t["muted"]},
        },
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{"show": True, "color": _solid(t["surface"]), "transparency": 0}],
                    "border": [{"show": True, "color": _solid(t["border"]), "radius": 12}],
                    "dropShadow": [{"show": False}],
                    "title": [{"show": True, "fontColor": _solid(t["text"]), "fontSize": 11, "fontFamily": bold}],
                    "subTitle": [{"show": False, "fontColor": _solid(t["muted"]), "fontSize": 9}],
                    "visualHeader": [
                        {
                            "background": _solid(t["surface"]),
                            "border": _solid(t["border"]),
                            "foreground": _solid(t["muted"]),
                            "transparency": 0,
                        }
                    ],
                    "visualTooltip": [
                        {
                            "titleFontColor": _solid(t["muted"]),
                            "valueFontColor": _solid(t["text"]),
                            "background": _solid(t["surface-2"]),
                        }
                    ],
                    "categoryAxis": [
                        {
                            "labelColor": _solid(t["muted"]),
                            "titleColor": _solid(t["muted"]),
                            "showAxisTitle": False,
                            "gridlineShow": False,
                        }
                    ],
                    "valueAxis": [
                        {
                            "labelColor": _solid(t["muted"]),
                            "titleColor": _solid(t["muted"]),
                            "showAxisTitle": False,
                            "gridlineShow": True,
                            "gridlineColor": _solid(t["border"]),
                            "gridlineStyle": "solid",
                            "gridlineThickness": 1,
                        }
                    ],
                    "legend": [{"labelColor": _solid(t["muted"]), "fontSize": 9, "position": "Bottom"}],
                    "labels": [{"color": _solid(t["text"])}],
                    "lineStyles": [{"strokeWidth": 2}],
                }
            },
            "page": {
                "*": {
                    "background": [{"color": _solid(t["bg"]), "transparency": 0}],
                    "outspace": [{"color": _solid(t["bg"]), "transparency": 0}],
                    "outspacePane": [
                        {
                            "backgroundColor": _solid(t["bg"]),
                            "foregroundColor": _solid(t["text"]),
                            "transparency": 0,
                            "border": True,
                            "borderColor": _solid(t["border"]),
                        }
                    ],
                    "filterCard": [
                        {
                            "$id": "Applied",
                            "transparency": 0,
                            "foregroundColor": _solid(t["text"]),
                            "backgroundColor": _solid(t["surface-2"]),
                            "inputBoxColor": _solid(t["surface"]),
                            "borderColor": _solid(t["border"]),
                            "border": True,
                        },
                        {
                            "$id": "Available",
                            "transparency": 0,
                            "foregroundColor": _solid(t["text"]),
                            "backgroundColor": _solid(t["surface"]),
                            "inputBoxColor": _solid(t["bg"]),
                            "borderColor": _solid(t["border"]),
                            "border": True,
                        },
                    ],
                }
            },
            "textbox": {
                "*": {
                    "background": [{"show": False}],
                    "border": [{"show": False}],
                    "dropShadow": [{"show": False}],
                }
            },
            "actionButton": {"*": {"border": [{"show": False}], "dropShadow": [{"show": False}]}},
            "slicer": {
                "*": {
                    "items": [{"fontColor": _solid(t["text"]), "background": _solid(t["surface"]), "textSize": 10}],
                    "header": [{"fontColor": _solid(t["muted"]), "textSize": 10}],
                }
            },
            "card": {
                "*": {
                    "labels": [{"color": _solid(t["text"]), "fontSize": 20, "labelDisplayUnits": 1}],
                    "categoryLabels": [{"show": False}],
                }
            },
            "tableEx": {
                "*": {
                    "grid": grid,
                    "columnHeaders": headers,
                    "values": [
                        {
                            "fontColorPrimary": _solid(t["text"]),
                            "backColorPrimary": _solid(t["surface"]),
                            "fontColorSecondary": _solid(t["text"]),
                            "backColorSecondary": _solid(t["surface-2"]),
                        }
                    ],
                    "total": total,
                }
            },
            "pivotTable": {
                "*": {
                    "grid": grid,
                    "columnHeaders": headers,
                    "rowHeaders": [{"fontColor": _solid(t["text"]), "backColor": _solid(t["surface"])}],
                    "values": [{"fontColorPrimary": _solid(t["text"]), "backColorPrimary": _solid(t["surface"])}],
                    "total": total,
                }
            },
        },
    }
    if PROJECT["theme"].get("display_units") == "none":
        every = theme["visualStyles"]["*"]["*"]
        every["labels"][0]["labelDisplayUnits"] = 1
        every["valueAxis"][0]["labelDisplayUnits"] = 1
    return theme


def render(theme: dict) -> str:
    return json.dumps(theme, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the report theme from the portfolio-kit tokens.")
    parser.add_argument("--check", action="store_true", help="compare a fresh build with the committed theme")
    args = parser.parse_args(argv)
    tokens = dark_tokens((ROOT / PROJECT["theme"]["tokens"]).read_text(encoding="utf-8"))
    text = render(build(tokens))
    path = theme_path()
    rel = path.relative_to(ROOT).as_posix()
    if args.check:
        if not path.is_file() or json.loads(path.read_text(encoding="utf-8-sig")) != json.loads(text):
            print(f"FAIL {rel} differs from a fresh build (uv run python tools/pbi/build_theme.py)")
            return 1
        print(f"{rel} matches the kit tokens")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    print(f"wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
