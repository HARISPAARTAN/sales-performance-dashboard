"""Independent pandas computation of the report's measures, the reference for tests, docs and the replica.

The semantics follow docs/measures.md: amounts are summed in integer cents, date filters are sets of
month indexes (1 = 2023-01, 36 = 2025-12), the time-intelligence items use whole months with sales
("Is past"), and a blank (None) behaves as in DAX: BLANK - x = -x, DIVIDE by blank or zero is blank.

Usage (from the repository root):
    uv run python tools/reference.py                  # the R01-R16 table of docs/reconciliation.md
    uv run python tools/reference.py --data tests/fixtures/mini
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from functools import cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIRST_YEAR = 2023
YEARS = (2023, 2024, 2025)
ALL_MONTHS = frozenset(range(1, 37))
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ITEMS = ("Current", "PY", "YoY", "YoY %", "YTD", "PYTD", "R12")
PCT_MEASURES = frozenset({"Gross margin %", "Discount %", "Target attainment %"})
GUARDED_MEASURES = frozenset(
    {
        "Product rank",
        "Pareto cumulative %",
        "Pareto class",
        "Products for 80 %",
        "Last sales date",
        "Data until",
        "Selected product",
    }
)

Value = int | float | str | dt.date | None


def month_index(year: int, month: int) -> int:
    return (year - FIRST_YEAR) * 12 + month


def months_for(years: Iterable[int] | None = None, month_from: int = 1, month_to: int = 12) -> frozenset[int]:
    """The month indexes a Year and Months selection keeps; years None means every year."""
    chosen = YEARS if years is None or not list(years) else tuple(years)
    return frozenset(month_index(y, m) for y in chosen for m in range(month_from, month_to + 1))


@dataclass(frozen=True)
class Context:
    """A filter context: month indexes plus value sets per dimension attribute (None = not filtered)."""

    months: frozenset[int] = ALL_MONTHS
    region: frozenset[str] | None = None
    country: frozenset[str] | None = None
    category: frozenset[str] | None = None
    subcategory: frozenset[str] | None = None
    product: frozenset[str] | None = None
    segment: frozenset[str] | None = None
    channel: frozenset[str] | None = None
    customer: frozenset[str] | None = None  # customer codes
    sales_rep: frozenset[str] | None = None  # sales rep names
    extra: tuple[tuple[str, frozenset[str]], ...] = field(default=())

    def where(self, **filters: Iterable[str] | frozenset[int] | None) -> Context:
        values = {key: (None if value is None else frozenset(value)) for key, value in filters.items()}
        return replace(self, **values)  # type: ignore[arg-type]

    @property
    def product_filtered(self) -> bool:
        return any(v is not None for v in (self.category, self.subcategory, self.product))

    @property
    def customer_filtered(self) -> bool:
        return any(v is not None for v in (self.country, self.segment, self.channel, self.customer))


FILTER_COLUMNS = {
    "region": "Region",
    "country": "Country",
    "category": "Category",
    "subcategory": "Subcategory",
    "product": "Product",
    "segment": "Segment",
    "channel": "Channel",
    "customer": "Customer code",
    "sales_rep": "Sales rep",
}


@dataclass
class Model:
    fact: pd.DataFrame  # one row per order line, keys and attributes joined, amounts in cents
    targets: pd.DataFrame  # month index, Region, target cents
    products: pd.DataFrame
    customers: pd.DataFrame
    regions: pd.DataFrame
    reps: pd.DataFrame
    security: pd.DataFrame
    last_month: int  # month index of the last order date
    last_date: dt.date


def _cents(series: pd.Series) -> pd.Series:
    return (series.astype("float64") * 100).round().astype("int64")


@cache
def load(data: Path = DATA) -> Model:
    """Read the workbooks under data/sales_orders/ and the CSV files, as Power Query does."""
    data = Path(data)
    books = sorted((data / "sales_orders").glob("*.xlsx"))
    if not books:
        raise FileNotFoundError(f"no workbooks in {data / 'sales_orders'}")
    frames = [pd.read_excel(book, sheet_name="Orders", header=2, engine="openpyxl") for book in books]
    lines = pd.concat(frames, ignore_index=True)
    products = pd.read_csv(data / "products.csv", keep_default_na=False, dtype={"DiscontinuedDate": str})
    customers = pd.read_csv(data / "customers.csv", keep_default_na=False)
    regions = pd.read_csv(data / "regions.csv", keep_default_na=False)
    reps = pd.read_csv(data / "sales_reps.csv", keep_default_na=False)
    security = pd.read_csv(data / "security.csv", keep_default_na=False)
    targets = pd.read_csv(data / "targets.csv", keep_default_na=False)

    region_of = regions.set_index("RegionCode")
    cust = customers.assign(
        RegionKey=customers["RegionCode"].map(region_of["RegionKey"]),
        Region=customers["RegionCode"].map(region_of["Region"]),
    )
    rep = reps.rename(columns={"SalesRepName": "Sales rep"})[["SalesRepCode", "SalesRepKey", "Sales rep"]]
    date = pd.to_datetime(lines["OrderDate"])
    fact = pd.DataFrame(
        {
            "Order number": lines["OrderNumber"].astype(str),
            "Order line": lines["OrderLine"].astype("int64"),
            "date": date.dt.date,
            "month": (date.dt.year - FIRST_YEAR) * 12 + date.dt.month,
            "CustomerCode": lines["CustomerCode"].astype(str),
            "SKU": lines["SKU"].astype(str),
            "SalesRepCode": lines["SalesRepCode"].astype(str),
            "quantity": lines["Quantity"].astype("int64"),
            "list_cents": _cents(lines["UnitListPriceEUR"]),
            "cost_unit_cents": _cents(lines["UnitCostEUR"]),
            "net": _cents(lines["NetAmountEUR"]),
        }
    )
    fact["gross"] = fact["quantity"] * fact["list_cents"]
    fact["cost"] = fact["quantity"] * fact["cost_unit_cents"]
    fact = (
        fact.merge(
            cust.rename(columns={"CustomerCode": "Customer code", "CustomerName": "Customer"})[
                [
                    "Customer code",
                    "CustomerKey",
                    "Customer",
                    "Segment",
                    "Channel",
                    "Country",
                    "RegionKey",
                    "Region",
                ]
            ],
            left_on="CustomerCode",
            right_on="Customer code",
            how="left",
            validate="many_to_one",
        )
        .merge(
            products.rename(columns={"ProductName": "Product"})[
                ["SKU", "ProductKey", "Product", "Category", "Subcategory"]
            ],
            on="SKU",
            how="left",
            validate="many_to_one",
        )
        .merge(rep, on="SalesRepCode", how="left", validate="many_to_one")
    )
    missing = fact[["CustomerKey", "ProductKey", "SalesRepKey"]].isna().any(axis=1)
    if missing.any():
        raise ValueError(f"{int(missing.sum())} order lines have a code without a master row")
    target_months = targets["Month"].str.slice(0, 4).astype(int) * 12 - FIRST_YEAR * 12
    target_frame = pd.DataFrame(
        {
            "month": target_months + targets["Month"].str.slice(5, 7).astype(int),
            "Region": targets["RegionCode"].map(region_of["Region"]),
            "target": targets["TargetRevenueEUR"].astype("int64") * 100,
        }
    )
    last_date = max(fact["date"])
    return Model(
        fact=fact,
        targets=target_frame,
        products=products,
        customers=cust,
        regions=regions,
        reps=reps,
        security=security,
        last_month=month_index(last_date.year, last_date.month),
        last_date=last_date,
    )


# ---------------------------------------------------------------- DAX-like helpers


def sub(a: Value, b: Value) -> Value:
    if a is None and b is None:
        return None
    return (a or 0) - (b or 0)  # type: ignore[operator]


def div(a: Value, b: Value) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b  # type: ignore[operator]


def _mask(model: Model, ctx: Context) -> pd.Series:
    fact = model.fact
    mask = fact["month"].isin(ctx.months)
    for name, column in FILTER_COLUMNS.items():
        values = getattr(ctx, name)
        if values is not None:
            mask &= fact[column].isin(values)
    return mask


def rows(model: Model, ctx: Context) -> pd.DataFrame:
    return model.fact[_mask(model, ctx)]


def _sum(frame: pd.DataFrame, column: str) -> int | None:
    return int(frame[column].sum()) if len(frame) else None


def _distinct(frame: pd.DataFrame, column: str) -> int | None:
    return int(frame[column].nunique()) if len(frame) else None


def _product_base(model: Model, ctx: Context) -> pd.Series:
    """Revenue per product over ALLEXCEPT(DimProduct, DimProduct[Category]); the category selection stays."""
    frame = rows(model, ctx.where(product=None))
    return frame.groupby("Product")["net"].sum().sort_values(ascending=False)


def _target(model: Model, ctx: Context) -> int | None:
    if ctx.product_filtered or ctx.customer_filtered or ctx.sales_rep is not None:
        return None
    t = model.targets[model.targets["month"].isin(ctx.months)]
    if ctx.region is not None:
        t = t[t["Region"].isin(ctx.region)]
    return int(t["target"].sum()) if len(t) else None


def _past(model: Model, ctx: Context) -> Context:
    return replace(ctx, months=frozenset(m for m in ctx.months if m <= model.last_month))


def _single_product(ctx: Context) -> str | None:
    return next(iter(ctx.product)) if ctx.product is not None and len(ctx.product) == 1 else None


def product_rank(model: Model, ctx: Context) -> int | None:
    name = _single_product(ctx)
    rev = measure(model, "Revenue", ctx)
    if name is None or rev is None:
        return None
    base = _product_base(model, ctx)
    return int((base > rev).sum()) + 1


def pareto_cumulative(model: Model, ctx: Context) -> float | None:
    name = _single_product(ctx)
    rev = measure(model, "Revenue", ctx)
    if name is None or rev is None:
        return None
    base = _product_base(model, ctx)
    return div(int(base[base >= rev].sum()), int(base.sum()))


def products_for_80(model: Model, ctx: Context) -> int | None:
    base = _product_base(model, ctx)
    base = base[base > 0]
    if base.empty:
        return 0
    total = int(base.sum())
    cumulative = [int(base[base >= value].sum()) for value in base]
    return sum(1 for c in cumulative if c <= 0.8 * total)


def _pareto_class(model: Model, ctx: Context) -> str | None:
    c = pareto_cumulative(model, ctx)
    if c is None:
        return None
    return "A" if c <= 0.8 else "B" if c <= 0.95 else "C"


MEASURES: dict[str, Callable[[Model, Context], Value]] = {
    "Revenue": lambda m, c: _sum(rows(m, c), "net"),
    "Gross sales": lambda m, c: _sum(rows(m, c), "gross"),
    "Cost": lambda m, c: _sum(rows(m, c), "cost"),
    "Gross margin": lambda m, c: sub(measure(m, "Revenue", c), measure(m, "Cost", c)),
    "Gross margin %": lambda m, c: div(measure(m, "Gross margin", c), measure(m, "Revenue", c)),
    "Discount %": lambda m, c: div(
        sub(measure(m, "Gross sales", c), measure(m, "Revenue", c)), measure(m, "Gross sales", c)
    ),
    "Units": lambda m, c: _sum(rows(m, c), "quantity"),
    "Orders": lambda m, c: _distinct(rows(m, c), "Order number"),
    "Average order value": lambda m, c: div(measure(m, "Revenue", c), measure(m, "Orders", c)),
    "Active customers": lambda m, c: _distinct(rows(m, c), "CustomerKey"),
    "Target": _target,
    "Target to date": lambda m, c: _target(m, _past(m, c)),
    "Target attainment %": lambda m, c: div(measure(m, "Revenue", c), measure(m, "Target to date", c)),
    "Target gap": lambda m, c: (
        sub(measure(m, "Revenue", c), ttd) if (ttd := measure(m, "Target to date", c)) is not None else None
    ),
    "Product rank": product_rank,
    "Pareto cumulative %": pareto_cumulative,
    "Pareto class": _pareto_class,
    "Products for 80 %": products_for_80,
    "Last sales date": lambda m, c: m.last_date,
    "Data until": lambda m, c: f"Data until {m.last_date.day} {MONTH_NAMES[m.last_date.month - 1]} {m.last_date.year}",
    "Selected product": lambda m, c: _single_product(c),
    "Order lines": lambda m, c: len(rows(m, c)) or None,
}
AMOUNT_MEASURES = frozenset(
    {
        "Revenue",
        "Gross sales",
        "Cost",
        "Gross margin",
        "Average order value",
        "Target",
        "Target to date",
        "Target gap",
    }
)


def measure(model: Model, name: str, ctx: Context) -> Value:
    return MEASURES[name](model, ctx)


def item(model: Model, name: str, calculation: str, ctx: Context) -> Value:
    """A measure under one item of the calculation group Time intelligence."""
    if calculation == "Current":
        return measure(model, name, ctx)
    past = sorted(m for m in ctx.months if m <= model.last_month)
    guard = not past or name in GUARDED_MEASURES
    if guard:
        return None
    pct = name in PCT_MEASURES
    last = past[-1]
    full = past[0] > 12
    cur = measure(model, name, replace(ctx, months=frozenset(past)))
    py = measure(model, name, replace(ctx, months=frozenset(m - 12 for m in past)))

    def window(first: int, end: int) -> Value:
        return measure(model, name, replace(ctx, months=frozenset(range(first, end + 1))))

    if calculation == "PY":
        return py
    if calculation == "YoY":
        if not full or cur is None or py is None:
            return None
        return (cur - py) * 100 if pct else cur - py  # type: ignore[operator]
    if calculation == "YoY %":
        return div(sub(cur, py), py) if (not pct and full) else None
    if calculation == "YTD":
        return window(last - (last - 1) % 12, last)
    if calculation == "PYTD":
        return window(last - 12 - (last - 1) % 12, last - 12)
    if calculation == "R12":
        return window(last - 11, last) if last >= 12 else None
    raise ValueError(f"unknown calculation item {calculation!r}")


def product_table(model: Model, ctx: Context) -> pd.DataFrame:
    """Rank, revenue, margin, units and Pareto values per product with revenue, by revenue descending."""
    frame = rows(model, ctx.where(product=None))
    grouped = frame.groupby(["Product", "SKU", "Category", "Subcategory"], as_index=False).agg(
        revenue=("net", "sum"), cost=("cost", "sum"), units=("quantity", "sum")
    )
    grouped = grouped.sort_values(["revenue", "SKU"], ascending=[False, True], ignore_index=True)
    total = int(grouped["revenue"].sum())
    revenue = grouped["revenue"]
    grouped["rank"] = [int((revenue > value).sum()) + 1 for value in revenue]
    grouped["cumulative"] = [int(revenue[revenue >= value].sum()) / total for value in revenue]
    grouped["class"] = ["A" if c <= 0.8 else "B" if c <= 0.95 else "C" for c in grouped["cumulative"]]
    grouped["margin"] = (grouped["revenue"] - grouped["cost"]) / grouped["revenue"]
    return grouped


# ---------------------------------------------------------------- reconciliation (docs/reconciliation.md)

RECONCILIATION = (
    ("R01", "Revenue 2024", "Revenue", "Current", Context(months=months_for([2024]))),
    ("R02", "Revenue 2025", "Revenue", "Current", Context(months=months_for([2025]))),
    ("R03", "Gross margin % 2024", "Gross margin %", "Current", Context(months=months_for([2024]))),
    ("R04", "Orders 2024", "Orders", "Current", Context(months=months_for([2024]))),
    ("R05", "Average order value 2024", "Average order value", "Current", Context(months=months_for([2024]))),
    ("R06", "Discount % 2024", "Discount %", "Current", Context(months=months_for([2024]))),
    (
        "R07",
        "Units 2024 Tents",
        "Units",
        "Current",
        Context(months=months_for([2024]), category=frozenset({"Tents"})),
    ),
    ("R08", "Revenue YoY % 2025", "Revenue", "YoY %", Context(months=months_for([2025]))),
    ("R09", "Revenue R12 September 2025", "Revenue", "R12", Context(months=months_for([2025], 9, 9))),
    ("R10", "Revenue PYTD 2025", "Revenue", "PYTD", Context(months=months_for([2025]))),
    (
        "R11",
        "Target 2025 DACH",
        "Target",
        "Current",
        Context(months=months_for([2025]), region=frozenset({"DACH"})),
    ),
    (
        "R12",
        "Target attainment % 2025 DACH",
        "Target attainment %",
        "Current",
        Context(months=months_for([2025]), region=frozenset({"DACH"})),
    ),
    ("R13", "Products for 80 % 2024", "Products for 80 %", "Current", Context(months=months_for([2024]))),
    ("R14", "Order lines", "Order lines", "Current", Context()),
)
RLS_CHECKS = (
    ("R15", "Revenue 2024 as the Nordics manager", ("NRD",)),
    ("R16", "Revenue 2024 as the West manager", ("BNL", "FRA")),
)


def rls_regions(model: Model, codes: tuple[str, ...]) -> frozenset[str]:
    """Region names a manager sees: the security rows of the e-mail that holds exactly these region codes."""
    by_user = model.security.groupby("UserEmail")["RegionCode"].apply(lambda s: tuple(sorted(s)))
    users = [user for user, held in by_user.items() if held == tuple(sorted(codes))]
    if len(users) != 1:
        raise ValueError(f"expected one manager for {codes}, found {len(users)}")
    names = model.regions.set_index("RegionCode")["Region"]
    return frozenset(names[code] for code in by_user[users[0]])


def reconciliation(model: Model) -> list[tuple[str, str, Value, str]]:
    """(id, check, value, kind) for R01-R16; kind is amount, count or ratio."""
    out: list[tuple[str, str, Value, str]] = []
    for rid, label, name, calc, ctx in RECONCILIATION:
        value = item(model, name, calc, ctx)
        kind = "ratio" if name in PCT_MEASURES or calc == "YoY %" else "amount" if name in AMOUNT_MEASURES else "count"
        out.append((rid, label, value, kind))
    for rid, label, codes in RLS_CHECKS:
        ctx = Context(months=months_for([2024]), region=rls_regions(model, codes))
        out.append((rid, label, measure(model, "Revenue", ctx), "amount"))
    return out


def display(value: Value, kind: str) -> str:
    """The Python column of docs/reconciliation.md: EUR to the cent, counts as integers, ratios to 6 dp."""
    if value is None:
        return "(blank)"
    if kind == "amount":
        cents = value if isinstance(value, float) else Decimal(value)  # type: ignore[arg-type]
        return f"{cents / 100:.2f}"
    if kind == "count":
        return str(int(value))  # type: ignore[arg-type]
    return f"{float(value):.6f}"  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the reconciliation values computed with pandas.")
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args(argv)
    model = load(args.data.resolve())
    print("| Id | Check | Python |")
    print("|---|---|---|")
    for rid, label, value, kind in reconciliation(model):
        print(f"| {rid} | {label} | {display(value, kind)} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
