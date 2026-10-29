"""Literals, selectors and filter aliases of the generated PBIR: decimals never use exponent notation, every value keeps
its type (text, number, true/false, date), and the filters of one visual do not share an alias."""

import datetime
import json

import pytest

import build_report
import pbir

pytestmark = pytest.mark.pbi


@pytest.mark.parametrize(
    ("value", "literal"),
    [(0, "0D"), (1, "1D"), (0.9, "0.9D"), (1.1, "1.1D"), (1_000_000, "1000000D"), (1234567.5, "1234567.5D")],
)
def test_number_literal(value, literal):
    assert build_report._number(value) == literal


def test_comparison_filter_literal_has_no_exponent():
    spec = {"field": ["_Measures", "Revenue"], "kind": "Measure", "op": ">=", "value": 2_500_000}
    text = json.dumps(pbir._comparison_filter("f0", spec))
    assert "2500000D" in text and "e+" not in text


@pytest.mark.parametrize(
    ("value", "literal"),
    [
        ("Current", "'Current'"),
        ("Tom's", "'Tom''s'"),
        (2025, "2025L"),
        (2.5, "2.5D"),
        (1234567.5, "1234567.5D"),
        (True, "true"),
        (False, "false"),
        (datetime.date(2025, 1, 1), "datetime'2025-01-01T00:00:00'"),
        (datetime.datetime(2025, 1, 31), "datetime'2025-01-31T00:00:00'"),
        (datetime.datetime(2025, 1, 31, 6, 30), "datetime'2025-01-31T06:30:00'"),
    ],
)
def test_quoted_keeps_the_type(value, literal):
    assert pbir._quoted(value) == literal


def test_slicer_selection_and_in_filter_use_typed_literals():
    values = [2.5, datetime.date(2025, 1, 1)]
    selection = pbir.slicer_selection("DimDate", "Date", values)
    literals = selection["filter"]["Where"][0]["Condition"]["In"]["Values"]
    assert [v[0]["Literal"]["Value"] for v in literals] == ["2.5D", "datetime'2025-01-01T00:00:00'"]
    in_filter = pbir._in_filter("x", {"field": ["DimDate", "Date"], "in": values})
    literals = in_filter["filter"]["Where"][0]["Condition"]["In"]["Values"]
    assert [v[0]["Literal"]["Value"] for v in literals] == ["2.5D", "datetime'2025-01-01T00:00:00'"]


@pytest.mark.parametrize(
    ("value", "literal"), [("Current", "'Current'"), (2025, "2025L"), (2.5, "2.5D"), (True, "true")]
)
def test_series_selector_is_typed_like_the_column(value, literal):
    scope = build_report._scope("DimDate", "Year", value)
    assert scope["data"][0]["scopeId"]["Comparison"]["Right"] == {"Literal": {"Value": literal}}


def test_series_colours_accept_pairs_for_number_legends():
    colours = build_report.Colours({"accent": "#111111", "muted": "#222222"})
    spec = {"field": ["DimDate", "Year"], "colours": [[2024, "muted"], [2025, "accent"]], "dashed": [2024]}
    objects = build_report._series(spec, colours)
    rights = [
        p["selector"]["data"][0]["scopeId"]["Comparison"]["Right"]["Literal"]["Value"] for p in objects["dataPoint"]
    ]
    assert rights == ["2024L", "2025L"]
    assert (
        objects["lineStyles"][1]["selector"]["data"][0]["scopeId"]["Comparison"]["Right"]["Literal"]["Value"] == "2024L"
    )


def test_formatting_metadata_is_the_query_ref_of_the_projection():
    colours = build_report.Colours(
        {
            "warn": "#111111",
            "surface": "#222222",
            "ok": "#333333",
            "accent": "#444444",
            "danger": "#555555",
            "border": "#666666",
        }
    )
    stops = {"min": [0.9, "warn"], "mid": [1, "surface"], "max": [1.1, "ok"]}
    column, measure = ["DimProduct", "Price", "Sum"], ["_Measures", "Revenue", "Measure"]
    for field, metadata in ((column, "Sum(DimProduct.Price)"), (measure, "_Measures.Revenue")):
        gradient = build_report._gradient({"field": field, **stops}, colours)
        assert gradient[0]["selector"]["metadata"] == metadata
        bars = build_report._data_bars({"field": field, "colour": "accent"}, colours)
        assert bars[0]["selector"]["metadata"] == metadata
        assert metadata == pbir.projection(*field)["queryRef"]


FILTERS = [
    {"field": ["Time intelligence", "Time calculation"], "in": ["Current", "PY"]},
    {"field": ["_Measures", "Revenue"], "kind": "Measure", "op": ">", "value": 0},
]


def test_filters_of_one_visual_have_their_own_alias():
    roles = {"Category": [("DimDate", "Month start", "Column")], "Y": [("_Measures", "Revenue", "Measure")]}
    visual = pbir.Visual.from_template("lineChart", "v", 0, 0, 100, 100, "Revenue", roles, filters=FILTERS)
    filters = visual["filterConfig"]["filters"]
    assert [f["filter"]["From"][0]["Name"] for f in filters] == ["f0", "f1"]
    assert set(pbir.iter_fields(visual["filterConfig"])) == {
        ("Time intelligence", "Time calculation", "Column"),
        ("_Measures", "Revenue", "Measure"),
    }


def test_iter_fields_resolves_an_alias_per_from():
    # the same alias for two tables, as the shared generator wrote it before the aliases became unique
    node = {
        "filters": [
            pbir._in_filter("a", {"field": ["DimRegion", "Region"], "in": ["DACH"]}, "f"),
            pbir._in_filter("b", {"field": ["DimProduct", "Category"], "in": ["Tents"]}, "f"),
        ]
    }
    resolved = [list(pbir.iter_fields(f["filter"])) for f in node["filters"]]
    assert resolved == [[("DimRegion", "Region", "Column")], [("DimProduct", "Category", "Column")]]
    assert set(pbir.iter_fields(node)) == {("DimRegion", "Region", "Column"), ("DimProduct", "Category", "Column")}
