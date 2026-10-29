"""DAXQueries/Reconciliation.dax holds R01-R14 in order, with the labels of tools/reference.py, and names only
tables, columns, measures and calculation items the model declares."""

import re
from pathlib import Path

import pytest

from pbir import PROJECT
from reference import RECONCILIATION
from tmdl import load_model

pytestmark = pytest.mark.pbi
SEMANTIC = Path(__file__).resolve().parents[2] / PROJECT["folder"] / f"{PROJECT['name']}.SemanticModel"
QUERY = SEMANTIC / "DAXQueries" / "Reconciliation.dax"
ROW = re.compile(r'ROW\("Id", "(R\d\d)", "Check", "([^"]+)",')
REF = re.compile(r"(?:'([^']+)'|(?<![\w\]'])([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
UNQUALIFIED = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
ITEM = re.compile(r"'Time intelligence'\[Time calculation\] = \"([^\"]+)\"")


@pytest.fixture(scope="module")
def query() -> str:
    return QUERY.read_text(encoding="utf-8")


def test_one_evaluate_of_a_union_ordered_by_id(query):
    code = "\n".join(line for line in query.splitlines() if not line.lstrip().startswith("//"))
    assert code.count("EVALUATE") == 1 and "UNION(" in code
    assert code.rstrip().endswith("ORDER BY [Id]")


def test_rows_are_r01_to_r14_with_the_reference_labels(query):
    rows = ROW.findall(query)
    assert rows == [(rid, label) for rid, label, *_ in RECONCILIATION]
    assert [rid for rid, _ in rows] == [f"R{n:02d}" for n in range(1, 15)]


def test_only_declared_names(query):
    model = load_model(SEMANTIC / "definition")
    code = "\n".join(line.split("//", 1)[0] for line in query.splitlines())
    for quoted, bare, item in REF.findall(code):
        table = quoted or bare
        assert table in model.tables and item in model.tables[table].columns, (table, item)
    measures = set(model.tables["_Measures"].measures)
    for name in UNQUALIFIED.findall(REF.sub("", code)):
        assert name in measures or name == "Id", name
    items = {i.name for i in model.tables["Time intelligence"].calculation_group.items}
    used = ITEM.findall(code)
    assert used == ["YoY %", "R12", "PYTD"] and set(used) <= items


def test_every_value_is_text_with_six_decimals_in_en_us(query):
    assert query.count('"0.000000", "en-US")') == 14
