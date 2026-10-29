"""Shared fixtures: the committed data loaded once, and the 14-line mini data set as workbooks."""

from __future__ import annotations

import csv
import datetime as dt
import shutil
from pathlib import Path

import pytest

import make_data
import reference

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "tests" / "fixtures" / "mini"
MINI_CSV = ("products.csv", "customers.csv", "regions.csv", "sales_reps.csv", "security.csv", "targets.csv")


def build_mini(target: Path) -> Path:
    """Copy the mini CSV files and write order_lines.csv as one export workbook per year."""
    (target / "sales_orders").mkdir(parents=True, exist_ok=True)
    for name in MINI_CSV:
        shutil.copy(MINI / name, target / name)
    by_year: dict[int, list[list[object]]] = {}
    with (MINI / "order_lines.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            date = dt.date.fromisoformat(row["OrderDate"])
            by_year.setdefault(date.year, []).append(
                [
                    row["OrderNumber"],
                    int(row["OrderLine"]),
                    date,
                    row["CustomerCode"],
                    row["SKU"],
                    row["SalesRepCode"],
                    int(row["Quantity"]),
                    float(row["UnitListPriceEUR"]),
                    float(row["DiscountRate"]),
                    float(row["UnitCostEUR"]),
                    float(row["NetAmountEUR"]),
                ]
            )
    for year, rows in by_year.items():
        make_data.write_workbook(target / "sales_orders" / f"sales_orders_{year}.xlsx", year, rows)
    return target


@pytest.fixture(scope="session")
def model() -> reference.Model:
    return reference.load(ROOT / "data")


@pytest.fixture(scope="session")
def mini(tmp_path_factory: pytest.TempPathFactory) -> reference.Model:
    return reference.load(build_mini(tmp_path_factory.mktemp("mini")))
