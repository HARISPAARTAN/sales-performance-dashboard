"""Optional: parse the TMDL folders with Microsoft's own TmdlSerializer (the parser Desktop uses).

Skipped unless build/tom/ holds the TOM client (tools/pbi/copy_tom.py) and pythonnet with a .NET runtime is
available (uv sync --group pbi). A TMDL syntax error fails here with the file, line and reason; Model.Validate()
reports semantic errors (unknown columns in DAX, broken sort-by columns, invalid relationships).
"""

import sys
from pathlib import Path

import pytest

import make_public_variant
from pbir import PROJECT

pytestmark = [pytest.mark.pbi, pytest.mark.tom]
ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "build" / "tom"
PBIP = ROOT / PROJECT["folder"] / f"{PROJECT['name']}.pbip"
MODEL = PBIP.parent / f"{PROJECT['name']}.SemanticModel" / "definition"


@pytest.fixture(scope="module")
def serializer():
    if not (LIB / "Microsoft.AnalysisServices.Tabular.dll").exists():
        pytest.skip("TOM client not in build/tom (uv run python tools/pbi/copy_tom.py --from <folder>)")
    try:
        from pythonnet import load

        try:
            load("coreclr")
        except RuntimeError:
            pass  # a runtime is already loaded in this process
        import clr
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"pythonnet or the .NET runtime is not available: {exc}")
    sys.path.append(str(LIB))
    clr.AddReference(str(LIB / "Microsoft.AnalysisServices.Tabular.dll"))
    from Microsoft.AnalysisServices.Tabular import TmdlSerializer

    return TmdlSerializer


def _errors(db) -> list[str]:
    result = db.Model.Validate()
    return [str(e.Message) for e in result.Errors] if result.ContainsErrors else []


def test_tom_parses_and_validates_the_model(serializer):
    db = serializer.DeserializeDatabaseFromFolder(str(MODEL))
    tables = {t.Name for t in db.Model.Tables}
    assert tables == {
        "DimDate",
        "DimProduct",
        "DimCustomer",
        "DimRegion",
        "DimSalesRep",
        "Security",
        "FactSales",
        "FactTargets",
        "_Measures",
        "Time intelligence",
        "Analyse by",
    }
    assert db.CompatibilityLevel == 1606
    assert _errors(db) == []


def test_tom_reads_the_measures_and_the_calculation_group(serializer):
    db = serializer.DeserializeDatabaseFromFolder(str(MODEL))
    tables = {t.Name: t for t in db.Model.Tables}
    measures = list(tables["_Measures"].Measures)
    assert len(measures) == 22
    assert all(str(m.Description) for m in measures)
    group = tables["Time intelligence"].CalculationGroup
    items = sorted(group.CalculationItems, key=lambda i: i.Ordinal)
    assert [i.Name for i in items] == ["Current", "PY", "YoY", "YoY %", "YTD", "PYTD", "R12"]
    assert group.Precedence == 10
    roles = {r.Name: r for r in db.Model.Roles}
    assert list(roles) == ["Regional manager"]
    assert {p.Table.Name for p in roles["Regional manager"].TablePermissions} == {
        "Security",
        "DimRegion",
        "DimCustomer",
        "DimSalesRep",
    }


def test_tom_parses_the_public_variant(serializer, tmp_path):
    pbip = make_public_variant.build(PBIP, tmp_path)
    folder = pbip.parent / pbip.name.replace(".pbip", ".SemanticModel") / "definition"
    db = serializer.DeserializeDatabaseFromFolder(str(folder))
    assert "Security" not in {t.Name for t in db.Model.Tables}
    assert len(list(db.Model.Roles)) == 0
    assert _errors(db) == []
