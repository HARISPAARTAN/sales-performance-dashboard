"""Offline lint of the PBIR report against spec section 6 and tools/pbi/pages.json. Each check is a function that
returns its problems, so the mutation tests at the end can prove that it bites."""

import copy
import json
import re
from pathlib import Path

import pytest

from build_report import bookmark_name, tile_specs
from pbir import PROJECT, ROLES, iter_fields, load_report, stable_name
from tmdl import load_model

pytestmark = pytest.mark.pbi
ROOT = Path(__file__).resolve().parents[2]
PBI = ROOT / PROJECT["folder"]
REPORT = PBI / f"{PROJECT['name']}.Report" / "definition"
MODEL = PBI / f"{PROJECT['name']}.SemanticModel" / "definition"
SPEC = json.loads((ROOT / "tools" / "pbi" / "pages.json").read_text(encoding="utf-8"))
PAGES = ["Overview", "Trends", "Products", "Regions", "Customers", "Targets", "Info", "Product tooltip"]
CONTENT_PAGES = PAGES[:6]
SYNC = {"Year", "Months", "Region", "Category"}
NOTE = "Demo with invented data for a fictional company"
FOOTER = "Rebuilt from memory as a demo. The original client's name and data are not used."
SLICER_ROW = (SPEC["slicer_row"]["y"], SPEC["slicer_row"]["y"] + SPEC["slicer_row"]["h"])
TILE_ROW = (SPEC["tiles"]["y"], SPEC["tiles"]["y"] + SPEC["tiles"]["h"])
CONTENT_TOP = 244


def lit(prop):
    return prop["expr"]["Literal"]["Value"]


def text_of(visual) -> str:
    paragraphs = (
        visual.raw["visual"].get("objects", {}).get("general", [{}])[0].get("properties", {}).get("paragraphs", [])
    )
    return "\n".join("".join(run["value"] for run in p["textRuns"]) for p in paragraphs)


def box(visual):
    p = visual.raw["position"]
    return p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]


@pytest.fixture(scope="module")
def report():
    return load_report(REPORT)


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL)


def page(report, name):
    return next(p for p in report.pages if p.display_name == name)


# --- checks ---------------------------------------------------------------------------------------------------------


def field_problems(raw, model, where=""):
    """Every Column, Measure and hierarchy Level node names an existing column, measure or level (kind-checked)."""
    out = []
    for entity, prop, kind in iter_fields(raw):
        table = model.tables.get(entity)
        if table is None:
            out.append(f"{where}: unknown table {entity!r}")
        elif kind == "Level":
            hierarchy, level = prop.split("/", 1)
            if level not in table.hierarchies.get(hierarchy, []):
                out.append(f"{where}: {entity} has no hierarchy level {prop!r}")
        elif prop not in (table.columns if kind == "Column" else table.measures):
            out.append(f"{where}: {entity}[{prop}] is used as a {kind} but the model has no such {kind.lower()}")
    return out


def layout_problems(pg):
    """Inside the canvas; slicers in the slicer row; tiles in the KPI row above the content; no two visuals overlap."""
    out = []
    boxes = []
    for v in pg.visuals:
        x0, y0, x1, y1 = box(v)
        if x0 < 0 or y0 < 0 or x1 > pg.width or y1 > pg.height:
            out.append(f"{pg.display_name}: {v.title} leaves the canvas")
        if v.visual_type == "slicer" and v.title in SYNC and (y0, y1) != SLICER_ROW:
            out.append(f"{pg.display_name}: slicer {v.title} is not in the slicer row")
        boxes.append((v.title or v.name, (x0, y0, x1, y1)))
    for i, (a, (ax0, ay0, ax1, ay1)) in enumerate(boxes):
        for b, (bx0, by0, bx1, by1) in boxes[i + 1 :]:
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                out.append(f"{pg.display_name}: {a!r} overlaps {b!r}")
    return out


def tile_problems(pg, spec_page):
    """The KPI tiles of the spec sit in the KPI row, each bound to its measure, with the calculation item filter."""
    out = []
    names = {v.name: v for v in pg.visuals}
    for key, tile in tile_specs(spec_page, SPEC["tiles"]):
        v = names.get(stable_name(pg.name, key))
        if v is None:
            out.append(f"{pg.display_name}: tile {key} is missing")
            continue
        x0, y0, x1, y1 = box(v)
        if y0 < TILE_ROW[0] or y1 > TILE_ROW[1] or y1 > CONTENT_TOP:
            out.append(f"{pg.display_name}: tile {key} is outside the KPI row")
        measure = tuple(tile["roles"]["Values"][0][:3])
        if [f for f in iter_fields(v.raw["visual"]["query"]) if f[2] == "Measure"] != [measure]:
            out.append(f"{pg.display_name}: tile {key} does not bind {measure}")
        wanted = [f["in"] for f in tile.get("filters", [])]
        found = [
            [
                w["Literal"]["Value"].strip("'")
                for row in flt["filter"]["Where"][0]["Condition"]["In"]["Values"]
                for w in row
            ]
            for flt in v.raw.get("filterConfig", {}).get("filters", [])
        ]
        if found != wanted:
            out.append(f"{pg.display_name}: tile {key} filters {found}, expected {wanted}")
    return out


def sync_problems(report):
    out = []
    for pg in report.pages:
        for v in pg.visuals:
            if v.visual_type != "slicer" or v.title not in SYNC:
                continue
            group = v.raw["visual"].get("syncGroup", {})
            if group != {"groupName": v.title, "fieldChanges": True, "filterChanges": True}:
                out.append(f"{pg.display_name}: slicer {v.title} has sync group {group}")
    return out


def reset_problems(report):
    """Each content page has one Reset button whose bookmark is its page's bookmark in the group Reset filters."""
    out = []
    by_name = {b["name"]: b for b in report.bookmarks}
    for pg in report.pages:
        if pg.display_name not in CONTENT_PAGES:
            continue
        buttons = [v for v in pg.visuals if v.visual_type == "actionButton"]
        if len(buttons) != 1:
            out.append(f"{pg.display_name}: {len(buttons)} buttons")
            continue
        link = buttons[0].raw["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]
        target = lit(link["bookmark"]).strip("'")
        if lit(link["type"]) != "'Bookmark'" or target != bookmark_name(pg.name):
            out.append(f"{pg.display_name}: Reset applies {target!r}")
        bm = by_name.get(target)
        if bm is None:
            out.append(f"{pg.display_name}: bookmark {target!r} does not exist")
            continue
        state = bm["explorationState"]
        if state["activeSection"] != pg.name or list(state["sections"]) != [pg.name]:
            out.append(f"{pg.display_name}: bookmark points at {state['activeSection']!r}")
            continue
        targets = set(bm["options"]["targetVisualNames"])
        restored = set(state["sections"][pg.name]["visualContainers"])
        if not bm["options"].get("applyOnlyToTargetVisuals") or targets != restored:
            out.append(f"{pg.display_name}: bookmark targets {sorted(targets)}")
        slicers = {v.name for v in pg.visuals if v.visual_type == "slicer" and v.title in SYNC}
        if not slicers <= targets:
            out.append(f"{pg.display_name}: bookmark misses slicers {sorted(slicers - targets)}")
    if report.bookmark_groups != {
        "Reset filters": [bookmark_name(p.name) for p in report.pages if p.display_name in CONTENT_PAGES]
    }:
        out.append(f"bookmark groups are {report.bookmark_groups}")
    return out


def tooltip_problems(report):
    out = []
    tip = page(report, "Product tooltip")
    if (tip.page_type, tip.visibility, tip.width, tip.height) != ("Tooltip", "HiddenInViewMode", 320, 240):
        out.append("the tooltip page is not a hidden 320 x 240 tooltip page")
    if (tip.raw.get("pageBinding") or {}).get("type") != "Tooltip":
        out.append("the tooltip page has no tooltip binding")
    for title in ("Pareto: top 40 products", "Products"):
        v = next(v for v in page(report, "Products").visuals if v.title == title)
        props = v.raw["visual"]["visualContainerObjects"].get("visualTooltip", [{}])[0].get("properties", {})
        if (
            lit(props.get("type", {"expr": {"Literal": {"Value": ""}}})) != "'ReportPage'"
            or lit(props["section"]).strip("'") != tip.name
        ):
            out.append(f"{title}: no report-page tooltip {tip.name!r}")
    return out


# --- the lint -------------------------------------------------------------------------------------------------------


def test_eight_pages_in_order_and_sizes(report):
    assert [p.display_name for p in report.pages] == PAGES
    assert [p.name for p in report.pages] == [p["id"] for p in SPEC["pages"]]
    for pg in report.pages[:-1]:
        assert (pg.width, pg.height, pg.page_type) == (1280, 720, None), pg.display_name


def test_every_bound_field_exists(report, model):
    problems = [p for pg in report.pages for v in pg.visuals for p in field_problems(v.raw, model, v.title or v.name)]
    problems += [p for b in report.bookmarks for p in field_problems(b, model, b["displayName"])]
    assert not problems, problems


def test_roles_are_valid_and_no_map_or_custom_visuals(report):
    for pg in report.pages:
        for v in pg.visuals:
            assert v.visual_type in ROLES, (pg.display_name, v.visual_type)
            assert v.roles() <= ROLES[v.visual_type], (pg.display_name, v.title, v.roles())
            assert "map" not in v.visual_type.lower(), v.visual_type


def test_layout_slicer_row_tiles_and_no_overlaps(report):
    problems = [p for pg in report.pages for p in layout_problems(pg)]
    spec_pages = {p["id"]: p for p in SPEC["pages"]}
    problems += [p for pg in report.pages for p in tile_problems(pg, spec_pages[pg.name])]
    assert not problems, problems


def test_content_pages_have_their_slicers(report):
    for pg in report.pages:
        slicers = sorted(v.title for v in pg.visuals if v.visual_type == "slicer" and v.title in SYNC)
        expected = {"Targets": ["Months", "Region", "Year"], "Info": [], "Product tooltip": []}.get(
            pg.display_name, ["Category", "Months", "Region", "Year"]
        )
        assert slicers == expected, pg.display_name
    targets = page(report, "Targets")
    assert any(
        "the category filter does not apply here" in text_of(v) for v in targets.visuals if v.visual_type == "textbox"
    )


def test_sync_groups(report):
    assert not sync_problems(report)


def test_reset_buttons_target_their_page_bookmark(report):
    assert not reset_problems(report)


def slicer_filter_values(properties: dict) -> list[str]:
    """The literal values of a slicer's `general.filter` selection; Desktop wraps the filter once more
    (`properties.filter.filter`) when it saves."""
    flt = properties["filter"]
    if "Where" not in flt:
        flt = flt["filter"]
    where = flt["Where"][0]["Condition"]["In"]["Values"]
    return [w["Literal"]["Value"] for row in where for w in row]


def test_reset_bookmarks_restore_the_default_state(report):
    for bm in report.bookmarks:
        pid = bm["explorationState"]["activeSection"]
        states = bm["explorationState"]["sections"][pid]["visualContainers"]
        year_name = stable_name(pid, "slicer", "Year")
        year = states[year_name]["singleVisual"]["objects"]["merge"]["general"][0]
        if year["properties"]:
            assert slicer_filter_values(year["properties"]) == ["2025L"], pid
        else:
            # Desktop stores a bookmark state that equals the slicer's own definition as an empty merge: the
            # Reset then restores the definition, so the definition must carry the 2025 selection.
            slicer = next(v for pg in report.pages if pg.name == pid for v in pg.visuals if v.name == year_name)
            assert slicer_filter_values(slicer.raw["visual"]["objects"]["general"][0]["properties"]) == ["2025L"], pid
        for name in ("Months", "Region", "Category"):
            state = states.get(stable_name(pid, "slicer", name))
            if state is not None:
                assert state["singleVisual"]["objects"] == {"remove": [{"object": "general", "property": "filter"}]}
    products = next(b for b in report.bookmarks if b["explorationState"]["activeSection"] == "products")
    drill = products["explorationState"]["sections"]["products"]["visualContainers"][stable_name("products", "2")]
    assert list(iter_fields(drill)) == [("DimProduct", "Products/Category", "Level")]
    overview = next(b for b in report.bookmarks if b["explorationState"]["activeSection"] == "overview")
    assert stable_name("overview", "2") in overview["options"]["targetVisualNames"]  # Analyse by


def test_tooltip_page_and_bindings(report):
    assert not tooltip_problems(report)


def test_kpi_deltas_use_calculation_items_not_extra_measures(report):
    overview = page(report, "Overview")
    deltas = sorted((v for v in overview.visuals if v.title and v.title.endswith(" vs PY")), key=lambda v: box(v)[0])
    for v in deltas:
        assert [f[2] for f in iter_fields(v.raw["visual"]["query"])] == ["Measure"], v.title
    assert [v.title for v in deltas] == [
        "Revenue vs PY",
        "Gross margin % vs PY",
        "Orders vs PY",
        "Avg. order value vs PY",
        "Discount % vs PY",
    ]


def test_charts_bind_what_section_6_says(report):
    def chart(page_name, title):
        return next(v for v in page(report, page_name).visuals if v.title == title)

    pareto = chart("Products", "Pareto: top 40 products")
    assert pareto.visual_type == "lineClusteredColumnComboChart"
    topn = [f for f in pareto.raw["filterConfig"]["filters"] if f["type"] == "TopN"]
    assert len(topn) == 1 and '"Top": 40' in json.dumps(topn[0]) and "Revenue" in json.dumps(topn[0])
    bars = chart("Products", "Revenue by category")
    assert list(iter_fields(bars.raw["visual"]["query"]["queryState"]["Category"])) == [
        ("DimProduct", "Products/Category", "Level"),
        ("DimProduct", "Products/Subcategory", "Level"),
    ]
    matrix = chart("Trends", "Revenue time intelligence")
    assert matrix.visual_type == "pivotTable" and matrix.raw["visual"]["expansionStates"][0]["roles"] == ["Rows"]
    analyse = chart("Overview", "Revenue by selected dimension")
    assert analyse.raw["visual"]["query"]["queryState"]["Category"]["fieldParameters"]
    attainment = chart("Targets", "Target attainment % by region")
    assert "Conditional" in json.dumps(attainment.raw["visual"]["objects"]["dataPoint"])
    heat = chart("Targets", "Attainment by region and month")
    assert "linearGradient3" in json.dumps(heat.raw["visual"]["objects"]["values"])


def test_alt_text_on_every_visual(report):
    missing = [(pg.display_name, v.visual_type, v.title) for pg in report.pages for v in pg.visuals if not v.alt_text]
    assert not missing, missing


def test_header_and_info_texts(report):
    for pg in report.pages[:-1]:
        texts = [text_of(v) for v in pg.visuals if v.visual_type == "textbox"]
        assert f"Veltrano Outdoor · {pg.display_name}" in texts, pg.display_name
        assert NOTE in texts, pg.display_name
    info = "\n".join(text_of(v) for v in page(report, "Info").visuals if v.visual_type == "textbox")
    for phrase in (
        "fictional outdoor-equipment wholesaler in Innsbruck, Austria",
        NOTE,
        FOOTER,
        "github.com/HARISPAARTAN/sales-performance-dashboard",
        "tools/make_data.py with seed 41",
    ):
        assert phrase in info, phrase
    assert not re.search(r"https?://", info)


def test_theme_registered_and_report_settings(report):
    assert report.theme_name == PROJECT["theme"]["file"]
    assert report.settings.get("defaultFilterActionIsDataFilter") is True
    theme = REPORT.parent / "StaticResources" / "RegisteredResources" / PROJECT["theme"]["file"]
    assert json.loads(theme.read_text(encoding="utf-8"))["name"] == PROJECT["theme"]["name"]


# --- mutations: each check catches a planted defect -----------------------------------------------------------------


def test_mutation_unknown_field_and_level_are_caught(report, model):
    v = copy.deepcopy(next(v for v in page(report, "Products").visuals if v.title == "Revenue by category").raw)
    text = json.dumps(v).replace('"Level": "Subcategory"', '"Level": "Brand"')
    assert field_problems(json.loads(text), model)
    text = json.dumps(v).replace('"Property": "Revenue"', '"Property": "Revenu"')
    assert field_problems(json.loads(text), model)


def test_mutation_overlap_and_slicer_outside_the_row_are_caught(report):
    pg = copy.deepcopy(page(report, "Overview"))
    slicer = next(v for v in pg.visuals if v.title == "Year")
    slicer.raw["position"]["y"] = 120
    problems = layout_problems(pg)
    assert any("not in the slicer row" in p for p in problems) and any("overlaps" in p for p in problems)


def test_mutation_missing_sync_group_and_wrong_bookmark_are_caught(report):
    broken = copy.deepcopy(report)
    slicer = next(v for v in broken.pages[0].visuals if v.title == "Region")
    del slicer.raw["visual"]["syncGroup"]
    assert sync_problems(broken)
    button = next(v for v in broken.pages[1].visuals if v.visual_type == "actionButton")
    button.raw["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]["bookmark"] = {
        "expr": {"Literal": {"Value": "'" + bookmark_name("overview") + "'"}}
    }
    assert reset_problems(broken)


def test_mutation_tooltip_page_shown_in_view_mode_is_caught(report):
    broken = copy.deepcopy(report)
    page(broken, "Product tooltip").visibility = None
    assert tooltip_problems(broken)


def test_mutation_tile_without_its_item_filter_is_caught(report):
    pg = copy.deepcopy(page(report, "Trends"))
    spec_page = next(p for p in SPEC["pages"] if p["id"] == "trends")
    tile = next(v for v in pg.visuals if v.name == stable_name("trends", "tile0"))
    del tile.raw["filterConfig"]
    assert tile_problems(pg, spec_page)
