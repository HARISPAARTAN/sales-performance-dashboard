"""Umbrella section 7: the replica's numbers come from replica.json, and replica.json equals the reference.

tests/replica/model.test.mjs runs web/assets/js/model.js on replica.json for the same 12 states and compares with
tests/replica/expected.json; this file proves that expected.json and the cubes themselves are the reference's numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import build_replica_data as brd
import reference as ref

ROOT = Path(__file__).resolve().parents[1]
STATE_NAMES = [
    "default", "2024", "2024 and 2025, months 1-9", "2025 Nordics", "2025 Tents",
    "2024 Q2, DACH and France, Apparel and Footwear", "all years", "2023", "September 2025", "drill Tents",
    "Targets 2025", "cross-filter Iberia",
]  # fmt: skip


@pytest.fixture(scope="module")
def replica() -> dict:
    return json.loads(brd.REPLICA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def expected() -> dict:
    return json.loads(brd.EXPECTED.read_text(encoding="utf-8"))


def by_year(cube: dict, column: str, first_year: int) -> dict[int, int]:
    """Sum of a cube column per calendar year; `rows` holds the row count of each month 1, 2, ..."""
    totals: dict[int, int] = {}
    start = 0
    for month, count in enumerate(cube["rows"], start=1):
        year = first_year + (month - 1) // 12
        totals[year] = totals.get(year, 0) + sum(cube[column][start : start + count])
        start += count
    return totals


def test_committed_files_equal_a_fresh_build(model):
    assert brd.REPLICA.read_text(encoding="utf-8") == brd.dumps_replica(brd.build(model))
    assert brd.EXPECTED.read_text(encoding="utf-8") == brd.dumps_expected(brd.expected(model))


@pytest.mark.parametrize("year", [2023, 2024, 2025])
def test_cube_totals_per_year_equal_the_reference(model, replica, year):
    ctx = ref.Context(months=ref.months_for([year]))
    first = replica["meta"]["firstYear"]
    revenue, cost, gross = (ref.measure(model, m, ctx) for m in ("Revenue", "Cost", "Gross sales"))
    units, orders = ref.measure(model, "Units", ctx), ref.measure(model, "Orders", ctx)
    for cube in ("S", "P", "C"):
        assert by_year(replica[cube], "net", first)[year] == revenue, cube
        assert by_year(replica[cube], "cost", first)[year] == cost, cube
    assert by_year(replica["S"], "gross", first)[year] == gross
    assert by_year(replica["C"], "gross", first)[year] == gross
    assert by_year(replica["S"], "units", first)[year] == units
    assert by_year(replica["P"], "units", first)[year] == units
    assert by_year(replica["C"], "orders", first)[year] == orders
    assert sum(replica["O"]["rows"][(year - first) * 12 : (year - first + 1) * 12]) == orders


def test_targets_equal_the_reference(model, replica):
    ctx = ref.Context(months=ref.months_for([2025]))
    whole_euros = sum(sum(series[24:36]) for series in replica["T"])
    assert whole_euros * 100 == ref.measure(model, "Target", ctx)


def test_twelve_states_in_the_order_of_the_spec(expected):
    assert expected["version"] == 1
    assert [s["name"] for s in expected["states"]] == STATE_NAMES
    assert [s["name"] for s in brd.STATES] == STATE_NAMES
    for entry in expected["states"]:
        assert set(entry["views"]) == set(brd.TABS), entry["name"]


def test_default_state_tiles_equal_the_reference(model, expected):
    tiles = expected["states"][0]["views"]["overview"]["tiles"]
    ctx = ref.Context(months=ref.months_for([2025]))
    names = {"revenue": "Revenue", "margin": "Gross margin %", "orders": "Orders", "aov": "Average order value",
             "discount": "Discount %"}  # fmt: skip
    for key, name in names.items():
        assert tiles[key]["value"] == pytest.approx(ref.measure(model, name, ctx), rel=1e-12), key
        assert tiles[key]["py"] == pytest.approx(ref.item(model, name, "PY", ctx), rel=1e-12), key
    assert tiles["revenue"]["delta"] == pytest.approx(ref.item(model, "Revenue", "YoY %", ctx), rel=1e-12)
    assert tiles["margin"]["delta"] == pytest.approx(ref.item(model, "Gross margin %", "YoY", ctx), rel=1e-12)


def test_replica_json_stays_in_budget():
    assert brd.REPLICA.stat().st_size <= 1_300_000
