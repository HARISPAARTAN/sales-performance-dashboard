"""Offline lint of the TMDL model against spec sections 4.2 and 7: tables, columns, relationships, measures,
calculation group, field parameter, role, partitions and DAX references."""

import re
from pathlib import Path

import pytest

from pbir import PROJECT
from tmdl import load_model

pytestmark = pytest.mark.pbi
MODEL_DIR = Path(__file__).resolve().parents[2] / PROJECT["folder"] / f"{PROJECT['name']}.SemanticModel" / "definition"
H = True  # hidden
# table -> column -> (data type, hidden, sort-by column)
COLUMNS = {
    "FactSales": {
        "Order number": ("string", False, None),
        "Order line": ("int64", H, None),
        "Order date": ("dateTime", False, None),
        "ProductKey": ("int64", H, None),
        "CustomerKey": ("int64", H, None),
        "RegionKey": ("int64", H, None),
        "SalesRepKey": ("int64", H, None),
        "Quantity": ("int64", H, None),
        "Unit list price": ("decimal", H, None),
        "Discount rate": ("double", H, None),
        "Unit cost": ("decimal", H, None),
        "Gross amount": ("decimal", H, None),
        "Net amount": ("decimal", H, None),
        "Cost amount": ("decimal", H, None),
    },
    "FactTargets": {
        "Month start": ("dateTime", H, None),
        "RegionKey": ("int64", H, None),
        "Target revenue": ("decimal", H, None),
    },
    "DimDate": {
        "Date": ("dateTime", False, None),
        "Year": ("int64", False, None),
        "Quarter": ("string", False, "Quarter number"),
        "Quarter number": ("int64", H, None),
        "Month": ("int64", False, None),
        "Month name": ("string", False, "Month"),
        "Month start": ("dateTime", False, None),
        "Year-month": ("string", False, "Month index"),
        "Month index": ("int64", H, None),
        "Is past": ("boolean", H, None),
    },
    "DimProduct": {
        "ProductKey": ("int64", H, None),
        "SKU": ("string", False, None),
        "Product": ("string", False, None),
        "Category": ("string", False, "Category sort"),
        "Category sort": ("int64", H, None),
        "Subcategory": ("string", False, "Subcategory sort"),
        "Subcategory sort": ("int64", H, None),
        "Brand": ("string", False, None),
        "List price": ("decimal", False, None),
        "Launch date": ("dateTime", False, None),
        "Discontinued date": ("dateTime", False, None),
        "Status": ("string", False, None),
    },
    "DimCustomer": {
        "CustomerKey": ("int64", H, None),
        "Customer code": ("string", False, None),
        "Customer": ("string", False, None),
        "Segment": ("string", False, "Segment sort"),
        "Segment sort": ("int64", H, None),
        "Channel": ("string", False, None),
        "Country code": ("string", False, None),
        "Country": ("string", False, None),
        "RegionKey": ("int64", H, None),
        "Account since": ("dateTime", False, None),
    },
    "DimRegion": {
        "RegionKey": ("int64", H, None),
        "Region code": ("string", False, None),
        "Region": ("string", False, "Region sort"),
        "Region sort": ("int64", H, None),
    },
    "DimSalesRep": {
        "SalesRepKey": ("int64", H, None),
        "Sales rep code": ("string", False, None),
        "Sales rep": ("string", False, None),
        "E-mail": ("string", False, None),
        "Home region": ("string", False, None),
        "RegionKey": ("int64", H, None),
    },
    "Security": {"User e-mail": ("string", False, None), "RegionKey": ("int64", False, None)},
    "_Measures": {"Anchor": ("int64", H, None)},
    "Time intelligence": {"Time calculation": ("string", False, "Ordinal"), "Ordinal": ("int64", H, None)},
    "Analyse by": {
        "Analyse by": ("string", False, "Analyse by Order"),
        "Analyse by Fields": ("string", H, "Analyse by Order"),
        "Analyse by Order": ("int64", H, None),
    },
}
RELATIONSHIPS = {
    ("FactSales.Order date", "DimDate.Date"),
    ("FactSales.ProductKey", "DimProduct.ProductKey"),
    ("FactSales.CustomerKey", "DimCustomer.CustomerKey"),
    ("FactSales.RegionKey", "DimRegion.RegionKey"),
    ("FactSales.SalesRepKey", "DimSalesRep.SalesRepKey"),
    ("FactTargets.Month start", "DimDate.Date"),
    ("FactTargets.RegionKey", "DimRegion.RegionKey"),
}
AMOUNT = (
    'VAR v = ABS(SELECTEDMEASURE()) RETURN IF(v >= 1E6, "€ #,0.00,,"" m""", IF(v >= 1E4, "€ #,0.0,"" k""", "€ #,0"))'
)
# measure -> (display folder, format string, or AMOUNT for the dynamic EUR format, or None for a text result)
MEASURES = {
    "Revenue": ("Sales", AMOUNT),
    "Gross sales": ("Sales", AMOUNT),
    "Cost": ("Sales", AMOUNT),
    "Gross margin": ("Sales", AMOUNT),
    "Gross margin %": ("Sales", "0.0 %"),
    "Discount %": ("Sales", "0.0 %"),
    "Units": ("Sales", "#,0"),
    "Orders": ("Sales", "#,0"),
    "Average order value": ("Sales", "€ #,0"),
    "Active customers": ("Sales", "#,0"),
    "Target": ("Targets", AMOUNT),
    "Target to date": ("Targets", AMOUNT),
    "Target attainment %": ("Targets", "0.0 %"),
    "Target gap": ("Targets", AMOUNT),
    "Product rank": ("Products", "0"),
    "Pareto cumulative %": ("Products", "0.0 %"),
    "Pareto class": ("Products", None),
    "Products for 80 %": ("Products", "#,0"),
    "Last sales date": ("Info", "d mmm yyyy"),
    "Data until": ("Info", None),
    "Selected product": ("Products", None),
    "Order lines": ("Info", "#,0"),
}
ITEMS = ["Current", "PY", "YoY", "YoY %", "YTD", "PYTD", "R12"]
GUARD = (
    "ISSELECTEDMEASURE([Product rank], [Pareto cumulative %], [Pareto class], [Products for 80 %], "
    "[Last sales date], [Data until], [Selected product])"
)
PCT = "ISSELECTEDMEASURE([Gross margin %], [Discount %], [Target attainment %])"
BODIES = {
    "PY": "IF(NOT guard, py)",
    "YoY": "IF(NOT guard && full && NOT ISBLANK(cur) && NOT ISBLANK(py), IF(pct, (cur - py) * 100, cur - py))",
    "YoY %": "IF(NOT guard && NOT pct && full, DIVIDE(cur - py, py))",
    "YTD": "DimDate[Month index] >= last - MOD(last - 1, 12)",
    "PYTD": "DimDate[Month index] >= last - 12 - MOD(last - 1, 12)",
    "R12": "IF(NOT guard && last >= 12, CALCULATE(",
}
REF = re.compile(r"(?:'([^']+)'|(?<![\w\]'])([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
UNQUALIFIED = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
ROLE_FILTER = "IN CALCULATETABLE(VALUES(Security[RegionKey]), Security[User e-mail] = USERPRINCIPALNAME())"


def flat(dax: str) -> str:
    """DAX on one line with single spaces, so a test can look for a phrase whatever the line breaks."""
    return re.sub(r"\s+", " ", re.sub(r"([({])\s+", r"\1", re.sub(r"\s+([)}])", r"\1", dax))).strip()


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL_DIR)


def test_tables_columns_types_and_sort_columns(model):
    assert set(model.tables) == set(COLUMNS)
    for table, columns in COLUMNS.items():
        assert set(model.tables[table].columns) == set(columns), table
        for name, (data_type, hidden, sort_by) in columns.items():
            col = model.tables[table].columns[name]
            assert (col.data_type, col.is_hidden, col.sort_by_column) == (data_type, hidden, sort_by), (table, name)


def test_hierarchies(model):
    assert model.tables["DimDate"].hierarchies == {"Calendar": ["Year", "Quarter", "Month name"]}
    assert model.tables["DimProduct"].hierarchies == {"Products": ["Category", "Subcategory", "Product"]}


def test_date_table_and_is_past(model):
    date = model.tables["DimDate"]
    assert date.data_category == "Time" and date.columns["Date"].is_key
    assert date.columns["Is past"].expression == "DimDate[Date] <= MAX(FactSales[Order date])"
    assert "CALCULATE" not in date.columns["Is past"].expression
    assert model.tables["DimProduct"].columns["List price"].summarize_by == "none"


def test_relationships_many_to_one_single_direction_with_hidden_keys(model):
    assert {(r.from_column, r.to_column) for r in model.relationships} == RELATIONSHIPS
    for r in model.relationships:
        assert r.cross_filtering_behavior in (None, "oneDirection") and r.is_active, r.name
        for side in (r.from_column, r.to_column):
            table, column = side.split(".", 1)
            if column.endswith("Key"):
                assert model.tables[table].columns[column].is_hidden, side
    assert not [r for r in model.relationships if "Security" in r.from_column + r.to_column]


def test_model_settings_and_parameters(model):
    assert model.culture == "en-US" and model.discourage_implicit_measures
    assert model.compatibility_level == 1606
    assert model.annotations.get("__PBI_TimeIntelligenceEnabled") == "0"
    params = model.expressions
    assert set(params) == {"DataFolder", "StartDate", "EndDate"}
    assert params["DataFolder"].expression.startswith('"E:\\GITGUB\\sales-performance-dashboard\\data\\" meta')
    assert params["StartDate"].expression.startswith("#date(2023, 1, 1) meta")  # a 1 January (calculation group)
    assert params["EndDate"].expression.startswith("#date(2025, 12, 31) meta")


def test_partitions_read_only_through_data_folder_with_culture(model):
    for name in ("FactSales", "FactTargets", "DimProduct", "DimCustomer", "DimRegion", "DimSalesRep", "Security"):
        source = model.tables[name].partition_source or ""
        assert model.tables[name].partition_kind == "m", name
        for call in re.findall(r"(?:File\.Contents|Folder\.Files)\(([^)]*)\)", source):
            assert call.startswith("DataFolder & "), (name, call)
        for typed in re.findall(r"Table\.TransformColumnTypes\((?:[^()]|\([^()]*\))*\)", source):
            assert typed.endswith('"en-US")'), (name, typed[:60])
    fact = model.tables["FactSales"].partition_source
    assert 'Folder.Files(DataFolder & "sales_orders")' in fact and "Currency.Type" in fact
    assert "Table.Skip(" in fact  # the two title rows above the header
    date = model.tables["DimDate"].partition_source
    assert "StartDate" in date and "EndDate" in date and "Month index" in date


def test_22_measures_with_description_folder_and_format(model):
    measures = model.tables["_Measures"].measures
    assert set(measures) == set(MEASURES)
    for name, (folder, fmt) in MEASURES.items():
        m = measures[name]
        assert m.description, name
        assert m.display_folder == folder, name
        if fmt == AMOUNT:
            assert m.format_string is None and flat(m.format_string_definition or "") == AMOUNT, name
        else:
            assert m.format_string == fmt and m.format_string_definition is None, name


def test_measure_definitions_of_section_7(model):
    m = {name: flat(x.expression) for name, x in model.tables["_Measures"].measures.items()}
    assert m["Revenue"] == "SUM(FactSales[Net amount])"
    assert m["Gross margin %"] == "DIVIDE([Gross margin], [Revenue])"
    assert m["Discount %"] == "DIVIDE([Gross sales] - [Revenue], [Gross sales])"
    assert m["Orders"] == "DISTINCTCOUNT(FactSales[Order number])"
    assert m["Target"].startswith("IF(ISFILTERED(DimProduct) || ISFILTERED(DimCustomer) || ISFILTERED(DimSalesRep)")
    assert m["Target to date"] == "CALCULATE([Target], DimDate[Is past] = TRUE())"
    for name in ("Product rank", "Pareto cumulative %", "Products for 80 %"):
        assert "REMOVEFILTERS(DimProduct[Product], DimProduct[SKU])" in m[name], name
    assert "RANKX(VALUES(DimProduct[Product]), [Revenue], rev, DESC, SKIP)" in m["Product rank"]
    assert 'IF(c <= 0.8, "A", IF(c <= 0.95, "B", "C"))' in m["Pareto class"]
    assert m["Data until"] == '"Data until " & FORMAT([Last sales date], "d mmm yyyy", "en-US")'


def test_calculation_group_items_in_order_with_their_guards(model):
    table = model.tables["Time intelligence"]
    group = table.calculation_group
    assert group is not None and group.precedence == 10
    assert [i.name for i in group.items] == ITEMS
    assert flat(group.items[0].expression) == "SELECTEDMEASURE()"
    for item in group.items[1:]:
        dax = flat(item.expression)
        assert f"VAR guard = ISEMPTY(past) || {GUARD}" in dax, item.name
        assert f"VAR pct = {PCT}" in dax and "VAR full = MINX(past, DimDate[Month index]) > 12" in dax, item.name
        assert BODIES[item.name] in dax, item.name
    formats = {i.name: flat(i.format_string_definition or "") for i in group.items}
    assert formats["YoY %"] == '"+0.0 %;-0.0 %;0.0 %"'
    assert formats["YoY"] == f'IF({PCT}, "+0.0"" pp"";-0.0"" pp"";0.0"" pp""", SELECTEDMEASUREFORMATSTRING())'
    assert all(not formats[n] for n in ("Current", "PY", "YTD", "PYTD", "R12"))


def test_field_parameter_entries(model):
    table = model.tables["Analyse by"]
    source = flat(table.partition_source or "")
    assert source == (
        "{(\"Category\", NAMEOF('DimProduct'[Category]), 0), (\"Region\", NAMEOF('DimRegion'[Region]), 1), "
        "(\"Segment\", NAMEOF('DimCustomer'[Segment]), 2), (\"Channel\", NAMEOF('DimCustomer'[Channel]), 3)}"
    )
    assert '"kind": 2' in (table.raw or "")


def test_role_filters_four_tables(model):
    assert [r.name for r in model.roles] == ["Regional manager"]
    role = model.roles[0]
    assert role.model_permission == "read"
    perms = {t: flat(e) for t, e in role.table_permissions.items()}
    assert perms == {
        "Security": "Security[User e-mail] = USERPRINCIPALNAME()",
        "DimRegion": f"DimRegion[RegionKey] {ROLE_FILTER}",
        "DimCustomer": f"DimCustomer[RegionKey] {ROLE_FILTER}",
        "DimSalesRep": f"DimSalesRep[RegionKey] {ROLE_FILTER}",
    }


def _expressions(model):
    out = [(f"measure {m.name}", m.expression) for m in model.tables["_Measures"].measures.values()]
    out += [(f"item {i.name}", i.expression) for i in model.tables["Time intelligence"].calculation_group.items]
    out += [(f"role {t}", e) for r in model.roles for t, e in r.table_permissions.items()]
    out += [
        (f"column {t.name}[{c.name}]", c.expression)
        for t in model.tables.values()
        for c in t.columns.values()
        if c.expression
    ]
    return out


def test_dax_references_resolve(model):
    cols = {(t, c) for t, tab in model.tables.items() for c in tab.columns}
    measures = {m for tab in model.tables.values() for m in tab.measures}
    for where, dax in _expressions(model):
        for quoted, bare, item in REF.findall(dax):
            table = quoted or bare
            assert (table, item) in cols, (where, table, item)
        for item in UNQUALIFIED.findall(REF.sub("", dax)):
            assert item in measures or item.startswith("@"), (where, item)


def test_mutation_unknown_column_is_caught(model):
    bad = [("measure X", "SUM(FactSales[Net amonut])")]
    cols = {(t, c) for t, tab in model.tables.items() for c in tab.columns}
    missing = [(w, t or b, i) for w, dax in bad for t, b, i in REF.findall(dax) if ((t or b), i) not in cols]
    assert missing == [("measure X", "FactSales", "Net amonut")]
