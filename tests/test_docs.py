"""The documentation agrees with the code: README outline in both languages, the DAX in docs/measures.md, the tables
and columns in docs/data-model.md, the decision records and the architecture diagram."""

import re
from pathlib import Path

import pytest

from pbir import PROJECT
from tmdl import load_model

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MODEL = ROOT / PROJECT["folder"] / f"{PROJECT['name']}.SemanticModel" / "definition"
FOOTER = "Rebuilt from memory as a demo. The original client's name and data are not used."
FENCE = "`" * 3
README_EN = [
    "Status",
    "Client brief",
    "Live demo",
    "What it does",
    "How it works",
    "Data model",
    "Getting started",
    "Project layout",
    "Decisions",
    "Compared with the original delivery",
    "Licence and data note",
]
README_DE = [
    "Status",
    "Kundenauftrag",
    "Live-Demo",
    "Was es kann",
    "So funktioniert es",
    "Datenmodell",
    "Erste Schritte",
    "Projektstruktur",
    "Entscheidungen",
    "Im Vergleich zur ursprünglichen Lieferung",
    "Lizenz und Hinweis zu den Daten",
]
ADRS = [
    "0001-yearly-order-workbooks.md",
    "0002-pandas-reference.md",
    "0003-month-index-time-intelligence.md",
    "0004-dynamic-rls.md",
    "0005-replica-cubes.md",
]


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def headings(text: str, level: int) -> list[str]:
    outside = re.sub(rf"{FENCE}.*?{FENCE}", "", text, flags=re.DOTALL)
    return re.findall(rf"^{'#' * level} (.+)$", outside, flags=re.MULTILINE)


def sections(text: str, level: int) -> dict[str, str]:
    parts = re.split(rf"^{'#' * level} ", text, flags=re.MULTILINE)[1:]
    return {part.split("\n", 1)[0].strip(): part for part in parts}


def code_lines(section: str) -> list[str]:
    """The lines of the first dax block of a section, each stripped (indentation is not compared)."""
    match = re.search(rf"{FENCE}dax\n(.*?)\n{FENCE}", section, flags=re.DOTALL)
    assert match, "no dax block"
    return [line.strip() for line in match.group(1).split("\n")]


def stripped(expression: str) -> list[str]:
    return [line.strip() for line in expression.split("\n")]


@pytest.mark.parametrize(("name", "outline"), [("README.md", README_EN), ("README.de.md", README_DE)])
def test_readme_follows_the_umbrella_outline(name, outline):
    text = read(ROOT / name)
    assert text.startswith("# Sales Performance Dashboard\n")
    assert headings(text, 2) == outline
    for badge in ("actions/workflows/ci.yml/badge.svg", "actions/workflows/pages.yml/badge.svg", "img.shields.io"):
        assert badge in text, badge
    other = "README.de.md" if name == "README.md" else "README.md"
    assert f"]({other})" in text
    assert text.rstrip().endswith(FOOTER)
    for adr in ADRS:
        assert f"](docs/adr/{adr})" in text, adr


def test_brief_is_the_same_in_the_readme_and_the_brief():
    quote = re.search(r"^> (.+)$", read(DOCS / "brief.md"), flags=re.MULTILINE).group(1)
    assert f"> {quote}" in read(ROOT / "README.md")
    assert FOOTER in read(DOCS / "brief.md")


def test_every_measure_is_documented_with_its_dax(model):
    doc = sections(read(DOCS / "measures.md"), 3)
    measures = model.tables["_Measures"].measures
    assert len(measures) == 22
    for name, measure in measures.items():
        assert name in doc, name
        assert code_lines(doc[name]) == stripped(measure.expression), f"{name}: the DAX differs from the TMDL"
        assert f"Folder `{measure.display_folder}`" in doc[name], name


def test_every_calculation_item_is_documented_with_its_dax(model):
    doc = sections(read(DOCS / "measures.md"), 3)
    items = model.tables["Time intelligence"].calculation_group.items
    assert [item.name for item in items] == ["Current", "PY", "YoY", "YoY %", "YTD", "PYTD", "R12"]
    for item in items:
        assert code_lines(doc[item.name]) == stripped(item.expression), f"{item.name}: the DAX differs from the TMDL"
        if item.format_string_definition:
            assert item.format_string_definition in doc[item.name], item.name


def test_field_parameter_and_role_are_documented(model):
    text = read(DOCS / "measures.md")
    doc = sections(text, 2)
    assert stripped(model.tables["Analyse by"].partition_source) == code_lines(doc["Field parameter Analyse by"])
    role = model.roles[0]
    filters = sections(doc[f"Role {role.name}"], 3)
    assert set(filters) == {f"Filter on {table}" for table in role.table_permissions}
    for table, expression in role.table_permissions.items():
        assert code_lines(filters[f"Filter on {table}"]) == stripped(expression), table


def test_data_model_lists_every_table_column_and_relationship(model):
    text = read(DOCS / "data-model.md")
    rows = {m.group(1): m.group(2) for m in re.finditer(r"^\| `([^`]+)` \| [^|]+ \| (.+) \|$", text, re.MULTILINE)}
    for name, table in model.tables.items():
        assert name in rows, name
        for column in table.columns:
            assert f"`{column}`" in rows[name], f"{name}[{column}]"
        for hierarchy in table.hierarchies:
            assert f"hierarchy `{hierarchy}`" in rows[name], hierarchy
    pairs = set(re.findall(r"^\| `(\w+)\[([^\]]+)\]` \| `(\w+)\[([^\]]+)\]` \|$", text, flags=re.MULTILINE))
    expected = {(*r.from_column.split(".", 1), *r.to_column.split(".", 1)) for r in model.relationships}
    assert pairs == expected


def test_data_model_lists_every_data_file():
    text = read(DOCS / "data-model.md")
    for path in sorted((ROOT / "data").glob("*.csv")):
        assert f"`data/{path.name}`" in text, path.name
    assert "`data/sales_orders/sales_orders_2023.xlsx`" in text


def test_decision_records():
    found = sorted(p.name for p in (DOCS / "adr").glob("*.md"))
    assert found == ADRS
    for name in ADRS:
        text = read(DOCS / "adr" / name)
        assert text.startswith(f"# ADR {name[:4]}: ")
        assert re.search(r"^Status: accepted \(\d{4}-\d{2}-\d{2}\)$", text, flags=re.MULTILINE), name
        assert headings(text, 2)[:3] == ["Context", "Decision", "Consequences"], name


def test_architecture_diagram_is_self_contained():
    svg = read(DOCS / "architecture.svg")
    assert svg.startswith("<svg ") and "<title" in svg and "<desc" in svg
    assert "http://" not in svg.replace("http://www.w3.org/2000/svg", "") and "https://" not in svg
    assert "<image" not in svg and "@import" not in svg
    for label in ("tools/make_data.py", "Power Query", "TMDL model", "PBIR report", "tools/reference.py"):
        assert label in svg, label
    for label in ("replica.json", "expected.json", "HTML replica", "Reconciliation R01 to R16"):
        assert label in svg, label


def test_docs_named_by_the_spec_exist():
    for name in ("brief.md", "data-model.md", "measures.md", "architecture.md", "handover.md"):
        assert (DOCS / name).is_file(), name
    for name in ("desktop-session.md", "reconciliation.md", "screenshots/SHOTLIST.md"):
        assert (DOCS / name).is_file(), name
    handover = headings(read(DOCS / "handover.md"), 2)
    for heading in ("Refresh", "Adding a year's export", "Changing targets", "Adding a regional manager"):
        assert heading in handover, heading
    assert "Building the role-free copy" in handover
