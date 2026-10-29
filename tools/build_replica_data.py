"""Build web/assets/data/replica.json and the expected replica states, tests/replica/expected.json.

replica.json holds dimension lists and columnar integer cubes in cents, rows sorted by month index with one
row count per month instead of a month column:
  S  month x country x category x segment x channel: net, gross, cost, units
  P  month x product x region: net, cost, units
  C  month x customer: net, gross, cost, orders
  O  one row per order: customer, category bit mask (bit i = category i)
  T  target per region and month in whole EUR (36 months)
expected.json holds the 12 filter states of the spec (section 10) and, for each, the six tab views computed
with tools/reference.py from the order lines (not from the cubes). tests/replica/model.test.mjs runs
web/assets/js/model.js on replica.json for the same states and must reproduce every value.

Usage (from the repository root):
    uv run python tools/build_replica_data.py           # write both files
    uv run python tools/build_replica_data.py --check   # exit 1 if either file differs from a fresh build
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

import reference as ref
from reference import Context, item, measure

ROOT = Path(__file__).resolve().parents[1]
REPLICA = ROOT / "web" / "assets" / "data" / "replica.json"
EXPECTED = ROOT / "tests" / "replica" / "expected.json"
CATEGORIES = ("Tents", "Sleeping", "Backpacks", "Apparel", "Footwear", "Cooking")
SEGMENTS = ("Independent", "Chain", "Online")
CHANNELS = ("Direct", "Distributor")
ANALYSE_COLUMNS = {"Category": "Category", "Region": "Region", "Segment": "Segment", "Channel": "Channel"}
TABS = ("overview", "trends", "products", "regions", "customers", "targets")
TOP_ROWS = 10
PARETO_ROWS = 40


def default_state() -> dict[str, Any]:
    return {
        "tab": "overview",
        "years": [2025],
        "monthFrom": 1,
        "monthTo": 12,
        "regions": [],
        "categories": [],
        "analyseBy": "Category",
        "cross": None,
        "drill": None,
    }


def state(name: str, **changes: Any) -> dict[str, Any]:
    return {"name": name, "state": {**default_state(), **changes}}


STATES = (
    state("default"),
    state("2024", years=[2024], tab="trends"),
    state("2024 and 2025, months 1-9", years=[2024, 2025], monthTo=9),
    state("2025 Nordics", regions=["Nordics"], tab="regions", analyseBy="Segment"),
    state("2025 Tents", categories=["Tents"], tab="products"),
    state(
        "2024 Q2, DACH and France, Apparel and Footwear",
        years=[2024],
        monthFrom=4,
        monthTo=6,
        regions=["DACH", "France"],
        categories=["Apparel", "Footwear"],
    ),
    state("all years", years=[], tab="trends", analyseBy="Channel"),
    state("2023", years=[2023]),
    state("September 2025", monthFrom=9, monthTo=9, tab="customers"),
    state("drill Tents", tab="products", drill="Tents"),
    state("Targets 2025", tab="targets"),
    state("cross-filter Iberia", analyseBy="Region", cross={"dim": "Region", "value": "Iberia"}),
)


# ---------------------------------------------------------------- replica.json


def _columns(frame: pd.DataFrame, names: list[str]) -> dict[str, list[int]]:
    return {name: [int(v) for v in frame[name]] for name in names}


def _month_rows(frame: pd.DataFrame, last_month: int) -> list[int]:
    counts = frame.groupby("month").size()
    return [int(counts.get(m, 0)) for m in range(1, last_month + 1)]


def build(model: ref.Model) -> dict[str, Any]:
    fact = model.fact[model.fact["month"] <= model.last_month]
    regions = list(model.regions.sort_values("SortOrder")["Region"])
    customers = model.customers.sort_values("CustomerKey").reset_index(drop=True)
    countries = (
        customers[["Country", "CountryCode", "Region"]]
        .drop_duplicates()
        .assign(region=lambda f: f["Region"].map(regions.index))
        .sort_values(["region", "Country"])
        .reset_index(drop=True)
    )
    country_index = {name: i for i, name in enumerate(countries["Country"])}
    products = model.products.sort_values("ProductKey").reset_index(drop=True)
    subcategories = (
        products[["Subcategory", "SubcategorySort", "Category"]]
        .drop_duplicates()
        .sort_values("SubcategorySort")
        .reset_index(drop=True)
    )
    sub_index = {name: i for i, name in enumerate(subcategories["Subcategory"])}
    reps = model.reps.sort_values("SalesRepKey").reset_index(drop=True)
    rep_region = model.regions.set_index("RegionCode")["Region"]
    rep_of = dict(zip(model.fact["CustomerKey"], model.fact["SalesRepKey"], strict=False))

    f = fact.assign(
        country=fact["Country"].map(country_index),
        cat=fact["Category"].map(CATEGORIES.index),
        seg=fact["Segment"].map(SEGMENTS.index),
        ch=fact["Channel"].map(CHANNELS.index),
        product=fact["ProductKey"] - 1,
        region=fact["RegionKey"] - 1,
        customer=fact["CustomerKey"] - 1,
    )
    s = f.groupby(["month", "country", "cat", "seg", "ch"], as_index=False)[["net", "gross", "cost", "quantity"]].sum()
    s = s.rename(columns={"quantity": "units"})
    p = f.groupby(["month", "product", "region"], as_index=False)[["net", "cost", "quantity"]].sum()
    p = p.rename(columns={"quantity": "units"})
    c = f.groupby(["month", "customer"], as_index=False).agg(
        net=("net", "sum"), gross=("gross", "sum"), cost=("cost", "sum"), orders=("Order number", "nunique")
    )
    o = (
        f.groupby("Order number", as_index=False)
        .agg(
            month=("month", "first"),
            customer=("customer", "first"),
            mask=("cat", lambda x: sum(1 << i for i in set(x))),
        )
        .sort_values(["month", "customer", "Order number"])
    )
    targets = model.targets.assign(region=model.targets["Region"].map(regions.index))
    t = [
        [int(v) // 100 for v in targets[targets["region"] == r].sort_values("month")["target"]]
        for r in range(len(regions))
    ]
    return {
        "version": 1,
        "meta": {
            "firstYear": ref.FIRST_YEAR,
            "lastMonth": model.last_month,
            "dataUntil": model.last_date.isoformat(),
            "targetMonths": 36,
        },
        "dims": {
            "regions": regions,
            "countries": [
                [n, cc, int(r)]
                for n, cc, r in zip(countries["Country"], countries["CountryCode"], countries["region"], strict=True)
            ],
            "categories": list(CATEGORIES),
            "subcategories": [
                [n, CATEGORIES.index(cat)]
                for n, cat in zip(subcategories["Subcategory"], subcategories["Category"], strict=True)
            ],
            "segments": list(SEGMENTS),
            "channels": list(CHANNELS),
            "products": {
                "sku": list(products["SKU"]),
                "name": list(products["ProductName"]),
                "sub": [sub_index[v] for v in products["Subcategory"]],
            },
            "reps": {
                "name": list(reps["SalesRepName"]),
                "region": [regions.index(rep_region[code]) for code in reps["RegionCode"]],
            },
            "customers": {
                "code": list(customers["CustomerCode"]),
                "name": list(customers["CustomerName"]),
                "segment": [SEGMENTS.index(v) for v in customers["Segment"]],
                "channel": [CHANNELS.index(v) for v in customers["Channel"]],
                "country": [country_index[v] for v in customers["Country"]],
                "rep": [int(rep_of.get(k, 0)) - 1 for k in customers["CustomerKey"]],
            },
        },
        "S": {
            "rows": _month_rows(s, model.last_month),
            **_columns(s, ["country", "cat", "seg", "ch", "net", "gross", "cost", "units"]),
        },
        "P": {
            "rows": _month_rows(p, model.last_month),
            **_columns(p, ["product", "region", "net", "cost", "units"]),
        },
        "C": {
            "rows": _month_rows(c, model.last_month),
            **_columns(c, ["customer", "net", "gross", "cost", "orders"]),
        },
        "O": {"rows": _month_rows(o, model.last_month), **_columns(o, ["customer", "mask"])},
        "T": t,
    }


# ---------------------------------------------------------------- expected states


def context(st: dict[str, Any], tab: str, *, cross: bool = True) -> Context:
    months = ref.months_for(st["years"] or None, st["monthFrom"], st["monthTo"])
    regions = set(st["regions"]) or None
    categories = set(st["categories"]) or None
    own = st["tab"] == tab
    if cross and own and st["cross"]:
        if st["cross"]["dim"] == "Region":
            regions = {st["cross"]["value"]}
        else:
            categories = {st["cross"]["value"]}
    if cross and own and tab == "products" and st["drill"]:
        categories = {st["drill"]}
    if tab in ("customers", "targets"):
        categories = None
    return Context(
        months=months,
        region=frozenset(regions) if regions else None,
        category=frozenset(categories) if categories else None,
    )


def past(model: ref.Model, ctx: Context) -> list[int]:
    return sorted(m for m in ctx.months if m <= model.last_month)


def tile(model: ref.Model, name: str, ctx: Context) -> dict[str, Any]:
    pct = name in ref.PCT_MEASURES
    delta = item(model, name, "YoY" if pct else "YoY %", ctx)
    months = past(model, ctx)
    note = None
    if delta is None:
        note = "no sales in the selected months" if not months else "no full previous year in the data"
        if months and months[0] > 12:
            note = "no previous-year value"
    return {
        "value": item(model, name, "Current", ctx),
        "py": item(model, name, "PY", ctx),
        "delta": delta,
        "note": note,
    }


def at(ctx: Context, months: set[int] | frozenset[int]) -> Context:
    return Context(months=frozenset(months), region=ctx.region, category=ctx.category)


def breakdown(model: ref.Model, ctx: Context, column: str, order: list[str]) -> list[list[Any]]:
    out = []
    for value in order:
        sub = Context(months=ctx.months, region=ctx.region, category=ctx.category).where(
            **{
                {
                    "Region": "region",
                    "Category": "category",
                    "Segment": "segment",
                    "Channel": "channel",
                    "Subcategory": "subcategory",
                }[column]: [value]
            }
        )
        if column == "Region" and ctx.region is not None and value not in ctx.region:
            continue
        if column == "Category" and ctx.category is not None and value not in ctx.category:
            continue
        revenue = measure(model, "Revenue", sub)
        if revenue is not None:
            out.append([value, revenue, measure(model, "Gross margin %", sub)])
    return sorted(out, key=lambda r: (-r[1], r[0]))


def overview(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx = context(st, "overview")
    tiles = {
        key: tile(model, name, ctx)
        for key, name in (
            ("revenue", "Revenue"),
            ("margin", "Gross margin %"),
            ("orders", "Orders"),
            ("aov", "Average order value"),
            ("discount", "Discount %"),
        )
    }
    months = [
        [
            m,
            item(model, "Revenue", "Current", at(ctx, {m})),
            item(model, "Revenue", "PY", at(ctx, {m})),
            measure(model, "Gross margin %", at(ctx, {m})),
        ]
        for m in past(model, ctx)
    ]
    dims = {
        "Category": list(CATEGORIES),
        "Region": list(model.regions.sort_values("SortOrder")["Region"]),
        "Segment": list(SEGMENTS),
        "Channel": list(CHANNELS),
    }
    source = context(st, "overview", cross=False)
    analyse = breakdown(model, source, ANALYSE_COLUMNS[st["analyseBy"]], dims[st["analyseBy"]])
    return {"tiles": tiles, "months": months, "analyse": analyse}


def trends(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx = context(st, "trends")
    tiles = {
        "ytd": {"value": item(model, "Revenue", "YTD", ctx), "delta": item(model, "Revenue", "YoY %", ctx)},
        "pytd": {"value": item(model, "Revenue", "PYTD", ctx)},
        "r12": {"value": item(model, "Revenue", "R12", ctx)},
        "units": tile(model, "Units", ctx),
    }
    rows = [[m, *(item(model, "Revenue", calc, at(ctx, {m})) for calc in ref.ITEMS)] for m in past(model, ctx)]
    units = []
    for m in past(model, ctx):
        frame = ref.rows(model, at(ctx, {m}))
        by_cat = frame.groupby("Category")["quantity"].sum()
        units.append([m, [int(by_cat[c]) if c in by_cat else None for c in CATEGORIES]])
    return {"tiles": tiles, "rows": rows, "units": units}


def products(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx = context(st, "products")
    tiles = {
        "revenue": tile(model, "Revenue", ctx),
        "units": tile(model, "Units", ctx),
        "margin": tile(model, "Gross margin %", ctx),
        "products80": measure(model, "Products for 80 %", ctx),
    }
    table = ref.product_table(model, ctx)
    pareto = [
        [sku, int(r), float(c)] for sku, r, c in zip(table["SKU"], table["revenue"], table["cumulative"], strict=True)
    ][:PARETO_ROWS]
    top = [
        [int(rank), sku, int(r), int(u), float(mg), float(c), cls]
        for rank, sku, r, u, mg, c, cls in zip(
            table["rank"],
            table["SKU"],
            table["revenue"],
            table["units"],
            table["margin"],
            table["cumulative"],
            table["class"],
            strict=True,
        )
    ][:TOP_ROWS]
    if st["tab"] == "products" and st["drill"]:
        subs = list(
            model.products[model.products["Category"] == st["drill"]]
            .sort_values("SubcategorySort")["Subcategory"]
            .unique()
        )
        bars = breakdown(model, ctx, "Subcategory", subs)
    else:
        bars = breakdown(model, context(st, "products", cross=False), "Category", list(CATEGORIES))
    return {"tiles": tiles, "pareto": pareto, "table": {"count": len(table), "top": top}, "bars": bars}


def regions(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx = context(st, "regions")
    tiles = {
        key: tile(model, name, ctx)
        for key, name in (
            ("revenue", "Revenue"),
            ("margin", "Gross margin %"),
            ("active", "Active customers"),
            ("aov", "Average order value"),
        )
    }
    source = context(st, "regions", cross=False)
    bars = []
    for region in model.regions.sort_values("SortOrder")["Region"]:
        if source.region is not None and region not in source.region:
            continue
        sub = source.where(region=[region])
        cur, py = item(model, "Revenue", "Current", sub), item(model, "Revenue", "PY", sub)
        if cur is not None or py is not None:
            bars.append([region, cur, py])
    frame = ref.rows(model, ctx)
    countries = []
    for (country, region), group in frame.groupby(["Country", "Region"]):
        net, cost, gross = int(group["net"].sum()), int(group["cost"].sum()), int(group["gross"].sum())
        orders = int(group["Order number"].nunique())
        countries.append(
            [
                country,
                region,
                net,
                (net - cost) / net,
                (gross - net) / gross,
                int(group["CustomerKey"].nunique()),
                net / orders,
            ]
        )
    countries.sort(key=lambda r: (-r[2], r[0]))
    return {"tiles": tiles, "bars": bars, "countries": countries}


def customers(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx = context(st, "customers")
    tiles = {
        key: tile(model, name, ctx)
        for key, name in (
            ("active", "Active customers"),
            ("revenue", "Revenue"),
            ("orders", "Orders"),
            ("aov", "Average order value"),
        )
    }
    frame = ref.rows(model, ctx)
    rows = []
    for code, group in frame.groupby("Customer code"):
        net, cost, gross = int(group["net"].sum()), int(group["cost"].sum()), int(group["gross"].sum())
        orders = int(group["Order number"].nunique())
        rows.append([code, net, (net - cost) / net, orders, net / orders, (gross - net) / gross])
    rows.sort(key=lambda r: (-r[1], r[0]))
    return {"tiles": tiles, "table": {"count": len(rows), "top": rows[:TOP_ROWS]}}


def targets(model: ref.Model, st: dict[str, Any]) -> dict[str, Any]:
    ctx = context(st, "targets")
    tiles = {
        "ttd": measure(model, "Target to date", ctx),
        "revenue": tile(model, "Revenue", ctx),
        "attainment": measure(model, "Target attainment %", ctx),
        "gap": measure(model, "Target gap", ctx),
        "target": measure(model, "Target", ctx),
    }
    months = [
        [m, measure(model, "Revenue", at(ctx, {m})), measure(model, "Target", at(ctx, {m}))] for m in sorted(ctx.months)
    ]
    order = [r for r in model.regions.sort_values("SortOrder")["Region"] if ctx.region is None or r in ctx.region]
    by_region = [[r, measure(model, "Target attainment %", ctx.where(region=[r]))] for r in order]
    matrix = [
        [r, m, measure(model, "Target attainment %", at(ctx, {m}).where(region=[r]))]
        for r in order
        for m in past(model, ctx)
    ]
    return {"tiles": tiles, "months": months, "regions": by_region, "matrix": matrix}


VIEWS = {
    "overview": overview,
    "trends": trends,
    "products": products,
    "regions": regions,
    "customers": customers,
    "targets": targets,
}


def expected(model: ref.Model) -> dict[str, Any]:
    out = []
    for entry in STATES:
        views = {tab: VIEWS[tab](model, entry["state"]) for tab in TABS}
        out.append({"name": entry["name"], "state": entry["state"], "views": views})
    return {"version": 1, "states": out}


def dumps_replica(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


def dumps_expected(data: dict[str, Any]) -> str:
    states = ",\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in data["states"])
    return '{"version":1,"states":[\n' + states + "\n]}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build web/assets/data/replica.json and tests/replica/expected.json.")
    parser.add_argument("--data", type=Path, default=ref.DATA)
    parser.add_argument("--check", action="store_true", help="compare a fresh build with the committed files")
    args = parser.parse_args(argv)
    model = ref.load(args.data.resolve())
    outputs = {REPLICA: dumps_replica(build(model)), EXPECTED: dumps_expected(expected(model))}
    if args.check:
        stale = [p for p, text in outputs.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        for path in stale:
            print(f"FAIL {path.relative_to(ROOT).as_posix()} differs from a fresh build")
        if stale:
            return 1
        print(f"replica.json ({len(outputs[REPLICA].encode()):,} bytes) and expected.json match a fresh build")
        return 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {REPLICA.relative_to(ROOT).as_posix()} ({len(outputs[REPLICA].encode()):,} bytes)")
    print(f"wrote {EXPECTED.relative_to(ROOT).as_posix()} ({len(STATES)} states)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
