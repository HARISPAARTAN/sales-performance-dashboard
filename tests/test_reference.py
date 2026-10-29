"""tools/reference.py on the 14-line mini data set (tests/fixtures/mini/order_lines.csv).

The lines, in EUR (net = quantity x list price x (1 - discount)):
  2023-12  SO-23-1: Alpha tent 200.00, Gamma jacket 50.00 (C0001, DACH)
           SO-23-2: Delta jacket 90.00 (C0003, Nordics)
  2024-01  SO-24-1: Beta tent 300.00, Gamma jacket 100.00 (C0002, DACH); SO-24-2: Alpha tent 100.00 (C0003)
  2024-02  SO-24-3: Delta jacket 50.00 (C0001)
  2024-12  SO-24-4: Alpha tent 80.00, Beta tent 80.00 (C0001, 20 % discount)
  2025-01  SO-25-1: Alpha tent 206.00, Delta jacket 103.00 (C0002); SO-25-2: Gamma jacket 154.50 (C0003)
  2025-02  SO-25-3: Beta tent 103.00, Gamma jacket 103.00 (C0001)
Month indexes: 2023-12 = 12, 2024-01 = 13, 2024-02 = 14, 2024-12 = 24, 2025-01 = 25,
2025-02 = 26 (the last month with sales).
"""

from __future__ import annotations

import datetime as dt

import pytest

import reference as ref
from reference import Context, item, measure, months_for

Y2023, Y2024, Y2025 = (Context(months=months_for([y])) for y in (2023, 2024, 2025))


def test_last_sales_date_and_month(mini: ref.Model) -> None:
    assert mini.last_date == dt.date(2025, 2, 3)
    assert mini.last_month == 26
    assert measure(mini, "Data until", Y2025) == "Data until 3 Feb 2025"
    assert measure(mini, "Order lines", Context()) == 14


def test_revenue_cost_and_margin(mini: ref.Model) -> None:
    assert measure(mini, "Revenue", Y2023) == 34_000
    assert measure(mini, "Revenue", Y2024) == 71_000
    assert measure(mini, "Revenue", Y2025) == 66_950
    assert measure(mini, "Cost", Y2024) == 45_400
    assert measure(mini, "Gross margin", Y2024) == 25_600
    assert measure(mini, "Gross margin %", Y2024) == pytest.approx(256 / 710)
    # Gross sales 2024 = 750.00 (two tents at full price before the 20 % discount)
    assert measure(mini, "Discount %", Y2024) == pytest.approx(40 / 750)


def test_orders_count_once_under_a_category_filter(mini: ref.Model) -> None:
    assert measure(mini, "Orders", Y2024) == 4
    assert measure(mini, "Orders", Y2024.where(category={"Tents"})) == 3  # SO-24-1, -2, -4
    assert measure(mini, "Orders", Y2024.where(category={"Apparel"})) == 2  # SO-24-1, -3
    assert measure(mini, "Active customers", Y2024) == 3


def test_average_order_value(mini: ref.Model) -> None:
    assert measure(mini, "Average order value", Y2024) == pytest.approx(17_750)
    assert measure(mini, "Average order value", Y2025.where(category={"Tents"})) == pytest.approx(30_900 / 2)


def test_previous_year_across_a_year_boundary(mini: ref.Model) -> None:
    dec_jan = Context(months=frozenset({24, 25}))
    assert item(mini, "Revenue", "Current", dec_jan) == 16_000 + 46_350
    assert item(mini, "Revenue", "PY", dec_jan) == 34_000 + 50_000  # 2023-12 and 2024-01
    assert item(mini, "Revenue", "YoY", dec_jan) == 62_350 - 84_000
    assert item(mini, "Revenue", "YoY %", dec_jan) == pytest.approx(-21_650 / 84_000)


def test_yoy_is_blank_without_a_full_previous_year(mini: ref.Model) -> None:
    assert item(mini, "Revenue", "YoY", Y2023) is None
    assert item(mini, "Revenue", "YoY %", Y2023) is None
    assert item(mini, "Revenue", "PY", Y2023) is None
    both = Context(months=months_for([2023, 2024]))
    assert item(mini, "Revenue", "YoY %", both) is None
    assert item(mini, "Revenue", "YoY %", Y2025) == pytest.approx((66_950 - 55_000) / 55_000)


def test_percentages_compare_in_points(mini: ref.Model) -> None:
    margin_2025 = (66_950 - 37_010) / 66_950
    margin_2024_jan_feb = (55_000 - 32_900) / 55_000
    assert item(mini, "Gross margin %", "YoY", Y2025) == pytest.approx((margin_2025 - margin_2024_jan_feb) * 100)
    assert item(mini, "Gross margin %", "YoY %", Y2025) is None


def test_ytd_pytd_and_r12(mini: ref.Model) -> None:
    assert item(mini, "Revenue", "YTD", Y2025) == 66_950
    assert item(mini, "Revenue", "PYTD", Y2025) == 55_000  # January and February 2024
    assert item(mini, "Revenue", "R12", Y2025) == 16_000 + 66_950  # 2024-03 to 2025-02
    december = Context(months=frozenset({24}))
    assert item(mini, "Revenue", "YTD", december) == 71_000
    assert item(mini, "Revenue", "PYTD", december) == 34_000
    assert item(mini, "Revenue", "R12", Context(months=frozenset({12}))) == 34_000
    assert item(mini, "Revenue", "R12", Context(months=frozenset({11}))) is None


def test_no_past_months_blank_every_comparison(mini: ref.Model) -> None:
    march = Context(months=frozenset({27}))
    assert item(mini, "Revenue", "Current", march) is None
    for calculation in ("PY", "YoY", "YoY %", "YTD", "PYTD", "R12"):
        assert item(mini, "Revenue", calculation, march) is None


def test_pareto_tie_and_rank_skip(mini: ref.Model) -> None:
    table = ref.product_table(mini, Y2025)
    assert list(table["SKU"]) == ["APP-JKT-001", "TEN-TRK-001", "APP-JKT-002", "TEN-TRK-002"]
    assert list(table["revenue"]) == [25_750, 20_600, 10_300, 10_300]
    assert list(table["rank"]) == [1, 2, 3, 3]
    assert list(table["cumulative"]) == pytest.approx([25_750 / 66_950, 46_350 / 66_950, 1.0, 1.0])
    assert list(table["class"]) == ["A", "A", "C", "C"]
    beta = Y2025.where(product={"Beta Trekking tent 3P"})
    assert measure(mini, "Product rank", beta) == 3
    assert measure(mini, "Pareto cumulative %", beta) == pytest.approx(1.0)
    assert measure(mini, "Products for 80 %", Y2025) == 2


def test_rank_and_pareto_are_blank_under_comparison_items(mini: ref.Model) -> None:
    beta = Y2025.where(product={"Beta Trekking tent 3P"})
    for calculation in ("PY", "YoY", "YTD"):
        assert item(mini, "Product rank", calculation, beta) is None
        assert item(mini, "Pareto cumulative %", calculation, beta) is None
    assert measure(mini, "Product rank", Y2025) is None  # no single product in context


def test_target_is_blank_under_a_product_or_customer_filter(mini: ref.Model) -> None:
    assert measure(mini, "Target", Y2025) == 600_000
    assert measure(mini, "Target", Y2025.where(region={"DACH"})) == 300_000
    assert measure(mini, "Target", Y2025.where(category={"Tents"})) is None
    assert measure(mini, "Target", Y2025.where(product={"Alpha Trekking tent 2P"})) is None
    assert measure(mini, "Target", Y2025.where(segment={"Chain"})) is None
    assert measure(mini, "Target to date", Y2025) == 400_000  # January and February
    assert measure(mini, "Target attainment %", Y2025) == pytest.approx(66_950 / 400_000)
    assert measure(mini, "Target gap", Y2025) == 66_950 - 400_000


def test_regional_manager_sees_own_regions(mini: ref.Model) -> None:
    assert ref.rls_regions(mini, ("NRD",)) == frozenset({"Nordics"})
    nordics_2024 = Y2024.where(region=ref.rls_regions(mini, ("NRD",)))
    assert measure(mini, "Revenue", nordics_2024) == 10_000


def test_display_formats() -> None:
    assert ref.display(1_175_590_246, "amount") == "11755902.46"
    assert ref.display(219_530.784, "amount") == "2195.31"
    assert ref.display(5355, "count") == "5355"
    assert ref.display(0.3536451234, "ratio") == "0.353645"
    assert ref.display(None, "ratio") == "(blank)"
