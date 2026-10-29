"""The committed data files: determinism, structure and every band of the spec (section 4.3)."""

from __future__ import annotations

import csv
import datetime as dt
import re
import zipfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

import make_data
import reference as ref

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WORKBOOKS = [DATA / "sales_orders" / f"sales_orders_{year}.xlsx" for year in (2023, 2024, 2025)]
AMBITION = {"DACH": 1.00, "Benelux": 1.02, "Nordics": 1.08, "France": 0.98, "Iberia": 1.04}


@pytest.fixture(scope="module")
def fact(model: ref.Model) -> pd.DataFrame:
    frame = model.fact.copy()
    frame["year"] = (frame["month"] - 1) // 12 + 2023
    frame["calendar_month"] = (frame["month"] - 1) % 12 + 1
    return frame


def read_csv(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# ---------------------------------------------------------------- determinism and files


def test_check_matches_a_fresh_build(capsys: pytest.CaptureFixture[str]) -> None:
    assert make_data.main(["--check"]) == 0
    assert "matches a fresh build" in capsys.readouterr().out


def test_workbook_entries_record_no_platform(tmp_path: Path) -> None:
    make_data.generate(tmp_path)
    for year, committed in zip((2023, 2024, 2025), WORKBOOKS, strict=True):
        fresh = tmp_path / "sales_orders" / f"sales_orders_{year}.xlsx"
        for path in (committed, fresh):
            with zipfile.ZipFile(path) as archive:
                assert {item.create_system for item in archive.infolist()} == {0}, path


def test_every_file_is_at_most_2_mb() -> None:
    files = [p for p in DATA.rglob("*") if p.is_file()]
    assert len(files) == 9
    for path in files:
        assert path.stat().st_size <= 2_000_000, path.name


def test_csv_files_are_utf8_lf_without_bom() -> None:
    for path in DATA.glob("*.csv"):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path.name
        assert b"\r\n" not in raw, path.name
        raw.decode("utf-8")


def test_workbook_layout(fact: pd.DataFrame) -> None:
    for year, path in zip((2023, 2024, 2025), WORKBOOKS, strict=True):
        wb = load_workbook(path, read_only=True)
        try:
            assert wb.sheetnames == ["Orders", "Export info"]
            rows = list(wb["Orders"].iter_rows(min_row=1, max_row=4, values_only=True))
            assert rows[0][0] == f"Veltrano Outdoor · Order lines export · {year}"
            assert rows[1][0] == "ERP export, EUR, net of discount"
            assert tuple(rows[2]) == make_data.ORDER_COLUMNS
            assert re.fullmatch(rf"SO-{year % 100:02d}-\d{{6}}", rows[3][0])
            info = {r[0]: r[1] for r in wb["Export info"].iter_rows(values_only=True)}
            assert info["Exported at"] == dt.datetime(2025, 10, 1, 6, 0)
            assert info["Rows"] == int((fact["year"] == year).sum())
        finally:
            wb.close()
        props = load_workbook(path).properties
        assert props.created == dt.datetime(2025, 10, 1, 6, 0)
        assert props.modified == dt.datetime(2025, 10, 1, 6, 0)


# ---------------------------------------------------------------- master data


def test_master_data_counts() -> None:
    products = read_csv("products.csv")
    assert len(products) == 180
    assert pd.Series([p["Category"] for p in products]).value_counts().to_dict() == dict.fromkeys(
        make_data.CATEGORIES, 30
    )
    assert len({p["Subcategory"] for p in products}) == 19
    assert pd.Series([p["Brand"] for p in products]).value_counts().to_dict() == {
        "Veltrano Trail": 81,
        "Veltrano Camp": 54,
        "Veltrano Summit": 45,
    }
    assert sum(1 for p in products if p["LaunchDate"] >= "2024-02-01") == 20
    assert sum(1 for p in products if p["DiscontinuedDate"]) == 12
    assert len({p["SKU"] for p in products}) == 180 and len({p["ProductName"] for p in products}) == 180
    customers = read_csv("customers.csv")
    assert len(customers) == 400
    by_country = pd.Series([c["CountryCode"] for c in customers]).value_counts().to_dict()
    assert by_country == {
        "DE": 85, "FR": 72, "AT": 55, "ES": 34, "NL": 30, "BE": 25, "SE": 22,
        "CH": 20, "NO": 15, "PT": 14, "DK": 13, "FI": 10, "LU": 5,
    }  # fmt: skip
    assert pd.Series([c["Segment"] for c in customers]).value_counts().to_dict() == {
        "Independent": 260,
        "Online": 100,
        "Chain": 40,
    }
    assert sum(1 for c in customers if c["AccountSince"] >= "2023-04-01") == 40
    assert len({c["CustomerName"] for c in customers}) == 400
    assert not any("Veltrano" in c["CustomerName"] for c in customers)
    assert len(read_csv("regions.csv")) == 5
    assert len(read_csv("sales_reps.csv")) == 12
    security = read_csv("security.csv")
    assert len(security) == 5 and len({s["UserEmail"] for s in security}) == 4


def test_one_region_per_country() -> None:
    pairs = {(c["CountryCode"], c["RegionCode"]) for c in read_csv("customers.csv")}
    countries = [country for country, _ in pairs]
    assert len(countries) == len(set(countries)) == 13


def test_channel_shares_per_region() -> None:
    customers = pd.DataFrame(read_csv("customers.csv"))
    direct = customers.assign(direct=customers["Channel"] == "Direct").groupby("RegionCode")["direct"].sum()
    assert direct.to_dict() == {"DACH": 152, "BNL": 48, "NRD": 18, "FRA": 50, "IBE": 12}


def test_every_code_resolves(model: ref.Model) -> None:
    # reference.load raises on a code without a master row; this pins the counts it joined.
    assert model.fact["CustomerKey"].notna().all()
    assert model.fact["ProductKey"].notna().all()
    assert model.fact["SalesRepKey"].notna().all()
    rep_region = pd.DataFrame(read_csv("sales_reps.csv")).set_index("SalesRepCode")["RegionCode"]
    cust_region = pd.DataFrame(read_csv("customers.csv")).set_index("CustomerCode")["RegionCode"]
    lines = model.fact[["CustomerCode", "SalesRepCode"]].drop_duplicates()
    assert (lines["CustomerCode"].map(cust_region) == lines["SalesRepCode"].map(rep_region)).all()


def test_emails_use_the_reserved_domain() -> None:
    emails = [r["Email"] for r in read_csv("sales_reps.csv")] + [r["UserEmail"] for r in read_csv("security.csv")]
    assert len(emails) == 17
    assert len(set(emails)) == 16  # the West manager holds two rows
    for email in emails:
        assert re.fullmatch(r"[a-z0-9-]+\.[a-z0-9-]+@veltrano\.example", email), email


def test_no_phone_numbers_or_street_addresses() -> None:
    phone = re.compile(r"\+\d{2}|\(\d{2,4}\)|\b\d{3,4}[ /-]\d{4,}\b")
    street = re.compile(r"(?i)\b(stra(ss|ß)e|street|road|avenue|rue|calle|gatan|straat|platz|via)\b")
    for path in DATA.glob("*.csv"):
        text = path.read_text(encoding="utf-8")
        assert not phone.search(text), path.name
        assert not street.search(text), path.name


# ---------------------------------------------------------------- order lines


def test_order_dates_are_weekdays_and_the_data_end_is_fixed(fact: pd.DataFrame) -> None:
    dates = pd.to_datetime(fact["date"])
    assert (dates.dt.day_of_week < 5).all()
    assert fact["date"].min() == dt.date(2023, 1, 2)
    assert fact["date"].max() == dt.date(2025, 9, 30)


def test_discounts_costs_and_net_amounts(fact: pd.DataFrame) -> None:
    frames = [pd.read_excel(p, sheet_name="Orders", header=2, dtype={"DiscountRate": str}) for p in WORKBOOKS]
    lines = pd.concat(frames, ignore_index=True)
    rates = lines["DiscountRate"].map(Decimal)
    assert rates.min() >= 0 and rates.max() <= Decimal("0.35")
    assert all(-r.as_tuple().exponent <= 4 for r in rates)
    assert (lines["UnitCostEUR"] < lines["UnitListPriceEUR"]).all()
    expected = [
        (Decimal(int(q)) * Decimal(f"{p:.2f}") * (1 - r)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for q, p, r in zip(lines["Quantity"], lines["UnitListPriceEUR"], rates, strict=True)
    ]
    actual = [Decimal(f"{n:.2f}") for n in lines["NetAmountEUR"]]
    assert expected == actual
    assert (fact["quantity"] >= 1).all()
    orders = fact.groupby("Order number")
    assert orders["SKU"].nunique().eq(orders.size()).all()  # distinct SKUs per order
    assert orders.size().max() <= 12


def test_targets_are_whole_thousands() -> None:
    targets = read_csv("targets.csv")
    assert len(targets) == 180
    assert {t["Month"] for t in targets} == {f"{y}-{m:02d}" for y in (2023, 2024, 2025) for m in range(1, 13)}
    assert all(int(t["TargetRevenueEUR"]) % 1000 == 0 and int(t["TargetRevenueEUR"]) > 0 for t in targets)


# ---------------------------------------------------------------- bands (spec 4.3)


def test_band_lines_orders_customers(fact: pd.DataFrame) -> None:
    assert 58_000 <= len(fact) <= 62_000
    assert 13_000 <= fact["Order number"].nunique() <= 16_500
    assert fact["CustomerKey"].nunique() >= 395


def test_band_revenue_and_growth(fact: pd.DataFrame) -> None:
    revenue = fact.groupby("year")["net"].sum()
    assert 1_050_000_000 <= revenue[2023] <= 1_400_000_000
    assert 0.06 <= revenue[2024] / revenue[2023] - 1 <= 0.10
    jan_sep_2024 = fact[(fact["year"] == 2024) & (fact["calendar_month"] <= 9)]["net"].sum()
    assert 0.06 <= revenue[2025] / jan_sep_2024 - 1 <= 0.10


def test_band_gross_margin_and_discount(fact: pd.DataFrame) -> None:
    by_year = fact.groupby("year")[["net", "cost", "gross"]].sum()
    margin = 1 - by_year["cost"] / by_year["net"]
    assert margin.between(0.30, 0.38).all()
    assert margin[2025] < margin[2023]
    discount = 1 - fact["net"].sum() / fact["gross"].sum()
    assert 0.08 <= discount <= 0.13


def test_band_average_order_value(fact: pd.DataFrame) -> None:
    by_year = fact.groupby("year").agg(net=("net", "sum"), orders=("Order number", "nunique"))
    aov = by_year["net"] / by_year["orders"] / 100
    assert aov.between(1_900, 3_200).all()
    assert 1_900 <= fact["net"].sum() / fact["Order number"].nunique() / 100 <= 3_200


@pytest.mark.parametrize(("category", "peaks"), [("Tents", {4, 5}), ("Apparel", {9, 10})])
def test_band_seasonal_peaks(fact: pd.DataFrame, category: str, peaks: set[int]) -> None:
    for year in (2023, 2024):
        rows = fact[(fact["Category"] == category) & (fact["year"] == year)]
        assert rows.groupby("calendar_month")["net"].sum().idxmax() in peaks, year


def test_band_top_products_and_dach_share(fact: pd.DataFrame) -> None:
    y2024 = fact[fact["year"] == 2024]
    by_product = y2024.groupby("ProductKey")["net"].sum().sort_values(ascending=False)
    assert 0.50 <= by_product.head(36).sum() / by_product.sum() <= 0.70
    by_region = y2024.groupby("Region")["net"].sum()
    assert 0.38 <= by_region["DACH"] / by_region.sum() <= 0.48


def test_band_target_attainment_2024(model: ref.Model, fact: pd.DataFrame) -> None:
    revenue = fact[fact["year"] == 2024].groupby("Region")["net"].sum()
    targets = model.targets[(model.targets["month"] >= 13) & (model.targets["month"] <= 24)]
    target = targets.groupby("Region")["target"].sum()
    for region, ambition in AMBITION.items():
        attainment = revenue[region] / target[region]
        assert abs(attainment - 1 / ambition) <= 0.04, region
