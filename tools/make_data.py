"""Generate the Veltrano Outdoor data files: three yearly order workbooks and six CSV files.

Usage (from the repository root):
    uv run python tools/make_data.py [--out data] [--check]

Seed 41 drives numpy.random.default_rng and NAME_SEED drives Faker (the 16 people), so every run writes the same
files; NAME_SEED changes names and e-mail addresses only, never a number (docs/data-model.md, "Generator tuning").
Workbooks carry the fixed time 2025-10-01 06:00 in their properties and zip entries. --check regenerates into a
temporary folder and compares the CSV files byte for byte and the workbooks by sheet names and cell values; it
exits 1 on the first difference.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import math
import re
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from faker import Faker
from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parents[1]
SEED = 41
NAME_SEED = 41  # raised only if a generated person name collides with the owner's never-committed banned list
TARGET_SEEDS = tuple(range(1041, 1061))
EXPORT_TIME = dt.datetime(2025, 10, 1, 6, 0)
FIRST_DAY = dt.date(2023, 1, 2)
LAST_DAY = dt.date(2025, 9, 30)
SIM_MONTHS = 36  # 2023-01 to 2025-12; the targets need the whole of 2025
EXPORT_MONTHS = 33  # 2023-01 to 2025-09
EXPECTED_LINES = 60_000
DOMAIN = "veltrano.example"
YEARS = (2023, 2024, 2025)


@dataclass(frozen=True)
class Region:
    key: int
    code: str
    name: str
    locale: str
    ambition: float
    direct_share: float
    countries: tuple[tuple[str, str, int], ...]
    chain: int
    reps: int
    season_shift: int  # +1: the season comes one month later, -1: one month earlier


REGIONS = (
    Region(
        1,
        "DACH",
        "DACH",
        "de_AT",
        1.00,
        0.95,
        (("AT", "Austria", 55), ("DE", "Germany", 85), ("CH", "Switzerland", 20)),
        16,
        4,
        0,
    ),
    Region(
        2,
        "BNL",
        "Benelux",
        "nl_NL",
        1.02,
        0.80,
        (("NL", "Netherlands", 30), ("BE", "Belgium", 25), ("LU", "Luxembourg", 5)),
        6,
        2,
        0,
    ),
    Region(
        3,
        "NRD",
        "Nordics",
        "sv_SE",
        1.08,
        0.30,
        (("SE", "Sweden", 22), ("NO", "Norway", 15), ("DK", "Denmark", 13), ("FI", "Finland", 10)),
        6,
        2,
        1,
    ),
    Region(4, "FRA", "France", "fr_FR", 0.98, 0.70, (("FR", "France", 72),), 8, 2, 0),
    Region(5, "IBE", "Iberia", "es_ES", 1.04, 0.25, (("ES", "Spain", 34), ("PT", "Portugal", 14)), 4, 2, -1),
)
# Regional managers: locale for the name and the regions each one leads (one security.csv row per region).
MANAGERS = (("de_AT", ("DACH",)), ("nl_NL", ("BNL", "FRA")), ("sv_SE", ("NRD",)), ("es_ES", ("IBE",)))

SEGMENTS = ("Independent", "Chain", "Online")
ONLINE_TOTAL = 100
ORDER_RATE = (0.85, 2.2, 1.35)  # orders per customer and month before season, trend, global factor (tuned)
LINES_EXTRA = (2.5, 4.5, 3.0)  # lines per order = 1 + Poisson(this), at most MAX_LINES
MAX_LINES = 12
QTY_SEGMENT = (1.0, 2.5, 1.5)
DISCOUNT_SEGMENT = (0.05, 0.12, 0.08)
TREND_PER_YEAR = -0.010  # tuned from +1.5 %: see docs/data-model.md, "Generator tuning"
JOINERS = 40
JOIN_FIRST, JOIN_LAST = 4, 30  # month index 4 = 2023-04, 30 = 2025-06

CATEGORIES = ("Tents", "Sleeping", "Backpacks", "Apparel", "Footwear", "Cooking")
CATEGORY_CODE = ("TEN", "SLP", "BPK", "APP", "FTW", "COK")
CATEGORY_SHARE = (0.12, 0.14, 0.15, 0.28, 0.15, 0.16)
CATEGORY_COST = (0.62, 0.59, 0.57, 0.52, 0.64, 0.54)
QTY_MEAN = (2.0, 3.0, 3.0, 5.0, 4.0, 6.0)
SUMMER = (0.55, 0.80, 1.20, 1.45, 1.55, 1.35, 1.00, 0.80, 0.75, 0.70, 0.70, 0.55)
APPAREL = (0.70, 0.85, 1.05, 1.05, 0.90, 0.75, 0.85, 1.15, 1.40, 1.35, 1.10, 0.70)
FOOTWEAR = (0.70, 0.90, 1.20, 1.30, 1.30, 1.10, 0.95, 0.90, 1.00, 0.95, 0.80, 0.60)
CATEGORY_SEASON = (SUMMER, SUMMER, SUMMER, APPAREL, FOOTWEAR, SUMMER)
CLEARANCE = 0.15  # share of eligible lines with the clearance discount

# (category index, subcategory, code, products, singular names cycled over the products, variants, price band)
SUBCATEGORIES = (
    (0, "Trekking tents", "TRK", 12, ("Trekking tent",), ("1P", "2P", "3P"), (180, 420)),
    (0, "Family tents", "FAM", 10, ("Family tent",), ("4P", "6P", "8P"), (250, 650)),
    (0, "Ultralight tents", "ULT", 8, ("Ultralight tent",), ("1P", "2P"), (280, 520)),
    (1, "Sleeping bags", "BAG", 14, ("Sleeping bag",), ("Summer", "Three-season", "Winter"), (60, 260)),
    (1, "Sleeping mats", "MAT", 10, ("Sleeping mat",), ("Regular", "Long", "Wide"), (30, 140)),
    (1, "Pillows and liners", "PIL", 6, ("Pillow", "Liner"), ("Compact", "Cotton", "Silk"), (12, 45)),
    (2, "Daypacks", "DAY", 12, ("Daypack",), ("18 L", "22 L", "28 L"), (35, 90)),
    (2, "Trekking packs", "TRK", 10, ("Trekking pack",), ("45 L", "55 L", "65 L"), (90, 220)),
    (2, "Travel packs", "TRV", 8, ("Travel pack",), ("35 L", "40 L", "50 L"), (70, 160)),
    (3, "Jackets", "JKT", 9, ("Jacket",), ("Hardshell", "Insulated", "Wind"), (80, 260)),
    (3, "Fleece and midlayers", "FLC", 7, ("Fleece", "Midlayer"), ("Light", "Grid", "Hooded"), (40, 110)),
    (3, "Trousers", "TRS", 8, ("Trousers",), ("Zip-off", "Softshell", "Winter"), (45, 120)),
    (3, "Base layers", "BSL", 6, ("Base layer",), ("Merino 150", "Merino 200", "Synthetic"), (25, 70)),
    (4, "Hiking boots", "HKB", 12, ("Hiking boot",), ("Low", "Mid", "High"), (80, 180)),
    (4, "Trail shoes", "TRL", 12, ("Trail shoe",), ("Grip", "Speed", "All-terrain"), (60, 120)),
    (4, "Sandals", "SND", 6, ("Sandal",), ("Strap", "Trek", "Slide"), (25, 60)),
    (5, "Stoves", "STV", 10, ("Stove",), ("Canister", "Multifuel", "Compact"), (30, 140)),
    (5, "Cookware", "CKW", 12, ("Cook set", "Pan", "Kettle"), ("1 L", "2 L", "Solo"), (15, 90)),
    (5, "Bottles and mugs", "BTL", 8, ("Bottle", "Mug"), ("0.5 L", "0.75 L", "1 L"), (8, 30)),
)
# (name, number of products, price factor, cost-ratio shift)
BRANDS = (
    ("Veltrano Summit", 45, 1.25, -0.03),
    ("Veltrano Trail", 81, 1.00, 0.0),
    ("Veltrano Camp", 54, 0.80, 0.04),
)
MODEL_WORDS = (
    "Torvel",
    "Larnik",
    "Senva",
    "Brelt",
    "Askel",
    "Borra",
    "Carno",
    "Drevin",
    "Elvik",
    "Fjarn",
    "Galdo",
    "Hevra",
    "Isvik",
    "Jorva",
    "Kelda",
    "Lomra",
    "Merin",
    "Narvo",
    "Osk",
    "Pellin",
    "Quarn",
    "Ravel",
    "Sorna",
    "Tavik",
    "Ulven",
    "Varn",
    "Welda",
    "Yrsel",
    "Zarno",
    "Arvo",
    "Belka",
    "Cindra",
    "Delvo",
    "Ernik",
    "Frosk",
    "Gelna",
    "Hamro",
    "Ivra",
    "Korva",
    "Lunda",
)
LAUNCHES, LAUNCH_FIRST, LAUNCH_LAST = 20, 14, 28  # 2024-02 to 2025-04
DISCONTINUED, DISC_FIRST, DISC_LAST = 12, 18, 27  # 2024-06 to 2025-03
LIST_RISE, COST_RISE = (103, 100), (1035, 1000)  # each 1 January: +3.0 % list, +3.5 % cost

STEM_A = (
    "Al",
    "Bran",
    "Cor",
    "Dal",
    "Eld",
    "Fal",
    "Grim",
    "Hal",
    "Isk",
    "Jor",
    "Kel",
    "Lun",
    "Mar",
    "Nor",
    "Orm",
    "Pel",
    "Ros",
    "Sil",
    "Tam",
    "Ul",
    "Var",
    "Wen",
    "Yst",
    "Zel",
)
STEM_B = (
    "bek",
    "dor",
    "fell",
    "gard",
    "holm",
    "jar",
    "kast",
    "lind",
    "mo",
    "nes",
    "ra",
    "sund",
    "tind",
    "vik",
    "wald",
    "by",
    "dal",
    "e",
    "ka",
    "lo",
    "ren",
    "stad",
)
INDEPENDENT_SUFFIX = {"DACH": ("Outdoor", "Bergsport", "Trail Shop")}
DEFAULT_SUFFIX = ("Outdoor", "Trail Shop")
SEGMENT_SUFFIX = {"Chain": "Sport Group", "Online": "Online"}


def month_start(index: int) -> dt.date:
    """Month index 1 = 2023-01."""
    return dt.date(2023 + (index - 1) // 12, (index - 1) % 12 + 1, 1)


def month_end(index: int) -> dt.date:
    return month_start(index + 1) - dt.timedelta(days=1)


def business_days(index: int) -> list[dt.date]:
    start = month_start(index)
    days = [start + dt.timedelta(days=i) for i in range((month_end(index) - start).days + 1)]
    return [day for day in days if day.weekday() < 5]


def half_up(numerator: int, denominator: int) -> int:
    """Integer division rounded half up, for non-negative integers."""
    return (2 * numerator + denominator) // (2 * denominator)


FOLD = (("ß", "ss"), ("Æ", "Ae"), ("æ", "ae"), ("Ø", "O"), ("ø", "o"), ("Ł", "L"), ("ł", "l"))


def ascii_fold(text: str) -> str:
    for source, target in FOLD:
        text = text.replace(source, target)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def email_for(first: str, last: str) -> str:
    parts = [re.sub(r"[^a-z0-9]+", "", ascii_fold(part).lower()) for part in (first, last)]
    return f"{parts[0]}.{parts[1]}@{DOMAIN}"


# ---------------------------------------------------------------- master data


@dataclass
class Master:
    regions: list[dict[str, object]]
    customers: list[dict[str, object]]
    products: list[dict[str, object]]
    reps: list[dict[str, object]]
    security: list[dict[str, object]]
    # arrays for the simulation, index = key - 1
    cust_region: np.ndarray
    cust_segment: np.ndarray
    cust_distributor: np.ndarray
    cust_start: np.ndarray
    cust_rep: np.ndarray
    prod_category: np.ndarray
    prod_popularity: np.ndarray
    prod_first: np.ndarray
    prod_last: np.ndarray
    list_cents: np.ndarray  # (3 years, products)
    cost_cents: np.ndarray


def build_master(rng: np.random.Generator) -> Master:
    regions: list[dict[str, object]] = [
        {"RegionKey": r.key, "RegionCode": r.code, "Region": r.name, "SortOrder": r.key} for r in REGIONS
    ]
    customers: list[dict[str, object]] = []
    cust_region: list[int] = []
    cust_segment: list[int] = []
    cust_distributor: list[int] = []
    stems = [a + b for a in STEM_A for b in STEM_B]
    stem_order = rng.permutation(len(stems))
    for ri, region in enumerate(REGIONS):
        size = sum(count for _, _, count in region.countries)
        online = round(ONLINE_TOTAL * size / 400)
        segments = np.array([1] * region.chain + [2] * online + [0] * (size - region.chain - online))
        segments = segments[rng.permutation(size)]
        direct = round(region.direct_share * size)
        distributor = np.array([0] * direct + [1] * (size - direct))[rng.permutation(size)]
        position = 0
        for country_code, country, count in region.countries:
            for _ in range(count):
                segment = SEGMENTS[segments[position]]
                key = len(customers) + 1
                stem = stems[stem_order[key - 1]]
                if segment == "Independent":
                    choices = INDEPENDENT_SUFFIX.get(region.code, DEFAULT_SUFFIX)
                    name = f"{stem} {choices[int(rng.integers(len(choices)))]}"
                else:
                    name = f"{stem} {SEGMENT_SUFFIX[segment]}"
                customers.append(
                    {
                        "CustomerKey": key,
                        "CustomerCode": f"C{key:04d}",
                        "CustomerName": name,
                        "Segment": segment,
                        "Channel": "Distributor" if distributor[position] else "Direct",
                        "CountryCode": country_code,
                        "Country": country,
                        "RegionCode": region.code,
                    }
                )
                cust_region.append(ri)
                cust_segment.append(int(segments[position]))
                cust_distributor.append(int(distributor[position]))
                position += 1
    joiners = np.sort(rng.choice(len(customers), JOINERS, replace=False))
    cust_start = np.ones(len(customers), dtype=np.int64)
    for k, index in enumerate(joiners):
        cust_start[index] = JOIN_FIRST + round(k * (JOIN_LAST - JOIN_FIRST) / (JOINERS - 1))
    for index, customer in enumerate(customers):
        if cust_start[index] > 1:
            since = business_days(int(cust_start[index]))[0]
        else:
            since = dt.date(int(rng.integers(2008, 2023)), int(rng.integers(1, 13)), 1)
        customer["AccountSince"] = since.isoformat()

    Faker.seed(NAME_SEED)
    fakers = {locale: Faker(locale) for locale in sorted({r.locale for r in REGIONS})}
    used: set[str] = set()

    def person(locale: str) -> tuple[str, str]:
        while True:
            first, last = fakers[locale].first_name(), fakers[locale].last_name()
            email = email_for(first, last)
            if email not in used:
                used.add(email)
                return f"{first} {last}", email

    reps: list[dict[str, object]] = []
    rep_by_region: list[list[int]] = []
    for region in REGIONS:
        keys = []
        for _ in range(region.reps):
            name, email = person(region.locale)
            key = len(reps) + 1
            reps.append(
                {
                    "SalesRepKey": key,
                    "SalesRepCode": f"R{key:02d}",
                    "SalesRepName": name,
                    "Email": email,
                    "RegionCode": region.code,
                }
            )
            keys.append(key - 1)
        rep_by_region.append(keys)
    security: list[dict[str, object]] = []
    for locale, codes in MANAGERS:
        _, email = person(locale)
        security.extend({"UserEmail": email, "RegionCode": code} for code in codes)
    counters = [0] * len(REGIONS)
    cust_rep = np.zeros(len(customers), dtype=np.int64)
    for index, ri in enumerate(cust_region):
        cust_rep[index] = rep_by_region[ri][counters[ri] % len(rep_by_region[ri])]
        counters[ri] += 1

    products: list[dict[str, object]] = []
    prod_category: list[int] = []
    list23: list[int] = []
    ratios: list[float] = []
    brand_labels = np.array([b for b, (_, count, _, _) in enumerate(BRANDS) for _ in range(count)])
    brand_labels = brand_labels[rng.permutation(len(brand_labels))]
    for sort, (ci, name, code, count, singulars, variants, (low, high)) in enumerate(SUBCATEGORIES, start=1):
        words = rng.choice(len(MODEL_WORDS), count, replace=False)
        for seq in range(count):
            key = len(products) + 1
            brand_name, _, factor, shift = BRANDS[brand_labels[key - 1]]
            base = rng.uniform(low, high) * factor
            ratio = CATEGORY_COST[ci] + shift + rng.uniform(-0.03, 0.03)
            products.append(
                {
                    "ProductKey": key,
                    "SKU": f"{CATEGORY_CODE[ci]}-{code}-{seq + 1:03d}",
                    "ProductName": f"{MODEL_WORDS[words[seq]]} {singulars[seq % len(singulars)]} "
                    f"{variants[seq % len(variants)]}",
                    "Category": CATEGORIES[ci],
                    "CategorySort": ci + 1,
                    "Subcategory": name,
                    "SubcategorySort": sort,
                    "Brand": brand_name,
                }
            )
            prod_category.append(ci)
            list23.append(math.floor(base + 0.5) * 100 - 10)  # whole euros minus 10 cents: 249.90
            ratios.append(ratio)
    n_products = len(products)
    popularity = rng.lognormal(0.0, 1.0, n_products)
    prod_first = np.ones(n_products, dtype=np.int64)
    prod_last = np.full(n_products, 10_000, dtype=np.int64)
    launched = np.sort(rng.choice(n_products, LAUNCHES, replace=False))
    for k, index in enumerate(launched):
        prod_first[index] = LAUNCH_FIRST + round(k * (LAUNCH_LAST - LAUNCH_FIRST) / (LAUNCHES - 1))
    others = np.setdiff1d(np.arange(n_products), launched)
    ended = np.sort(rng.choice(others, DISCONTINUED, replace=False))
    for k, index in enumerate(ended):
        prod_last[index] = DISC_FIRST + round(k * (DISC_LAST - DISC_FIRST) / (DISCONTINUED - 1))
    list_cents = np.zeros((3, n_products), dtype=np.int64)
    cost_cents = np.zeros((3, n_products), dtype=np.int64)
    for index in range(n_products):
        list_cents[0, index] = list23[index]
        cost_cents[0, index] = math.floor(list23[index] * ratios[index] + 0.5)
        for year in (1, 2):
            list_cents[year, index] = half_up(int(list_cents[year - 1, index]) * LIST_RISE[0], LIST_RISE[1])
            cost_cents[year, index] = half_up(int(cost_cents[year - 1, index]) * COST_RISE[0], COST_RISE[1])
    for index, product in enumerate(products):
        product["ListPriceEUR"] = f"{list_cents[2, index] / 100:.2f}"
        if prod_first[index] > 1:
            product["LaunchDate"] = month_start(int(prod_first[index])).isoformat()
        else:
            launch = dt.date(int(rng.integers(2016, 2023)), int(rng.integers(1, 13)), 1)
            product["LaunchDate"] = launch.isoformat()
        last = int(prod_last[index])
        product["DiscontinuedDate"] = month_end(last).isoformat() if last < 10_000 else ""
    return Master(
        regions,
        customers,
        products,
        reps,
        security,
        np.array(cust_region),
        np.array(cust_segment),
        np.array(cust_distributor),
        cust_start,
        cust_rep,
        np.array(prod_category),
        popularity,
        prod_first,
        prod_last,
        list_cents,
        cost_cents,
    )


# ---------------------------------------------------------------- order simulation


def season_index() -> np.ndarray:
    """(regions, months, categories): each category's index, normalised to mean 1 and shifted per region."""
    base = np.array([np.array(s) / np.mean(s) for s in CATEGORY_SEASON])  # (categories, 12)
    out = np.zeros((len(REGIONS), SIM_MONTHS, len(CATEGORIES)))
    for ri, region in enumerate(REGIONS):
        for m in range(SIM_MONTHS):
            out[ri, m] = base[:, (m % 12 - region.season_shift) % 12]
    return out


def expected_lines_per_order(extra: float) -> float:
    pmf = [math.exp(-extra) * extra**k / math.factorial(k) for k in range(MAX_LINES - 1)]
    return sum((k + 1) * p for k, p in enumerate(pmf)) + MAX_LINES * (1 - sum(pmf))


def order_rates(master: Master) -> np.ndarray:
    """Poisson rate per customer and month (customers, months), global factor included."""
    mix = season_index() @ np.array(CATEGORY_SHARE)  # (regions, months)
    trend = (1 + TREND_PER_YEAR) ** (np.arange(SIM_MONTHS) / 12)
    active = np.arange(1, SIM_MONTHS + 1)[None, :] >= master.cust_start[:, None]
    base = np.array(ORDER_RATE)[master.cust_segment][:, None]
    raw = base * mix[master.cust_region] * trend[None, :] * active
    lines = np.array([expected_lines_per_order(x) for x in LINES_EXTRA])[master.cust_segment]
    factor = EXPECTED_LINES / float((raw[:, :EXPORT_MONTHS] * lines[:, None]).sum())
    return raw * factor


def product_log_weights(master: Master) -> np.ndarray:
    """(regions, months, products): log of category weight x popularity share among the active products."""
    idx = season_index()
    months = np.arange(1, SIM_MONTHS + 1)
    active = (master.prod_first[None, :] <= months[:, None]) & (master.prod_last[None, :] >= months[:, None])
    pop = master.prod_popularity[None, :] * active  # (months, products)
    cat_pop = np.zeros((SIM_MONTHS, len(CATEGORIES)))
    for ci in range(len(CATEGORIES)):
        cat_pop[:, ci] = pop[:, master.prod_category == ci].sum(axis=1)
    category_weight = (np.array(CATEGORY_SHARE)[None, None, :] * idx)[:, :, master.prod_category]
    weight = category_weight * (pop / cat_pop[:, master.prod_category])[None]
    with np.errstate(divide="ignore"):
        return np.log(weight)


def simulate(rng: np.random.Generator, master: Master) -> dict[str, np.ndarray]:
    """All order lines of 2023-01 to 2025-12 as arrays, orders sorted by date and customer."""
    counts = rng.poisson(order_rates(master))
    flat = np.repeat(np.arange(counts.size), counts.ravel())
    cust, month = flat // SIM_MONTHS, flat % SIM_MONTHS + 1
    calendars = [business_days(m) for m in range(1, SIM_MONTHS + 1)]
    sizes = np.array([len(c) for c in calendars])
    day = rng.integers(0, sizes[month - 1])
    # The data end is fixed: one order on the first and one on the last business day.
    day[np.flatnonzero(month == 1)[0]] = 0
    day[np.flatnonzero(month == EXPORT_MONTHS)[-1]] = sizes[EXPORT_MONTHS - 1] - 1
    ordinal = np.array([calendars[m - 1][d].toordinal() for m, d in zip(month, day, strict=True)])
    order = np.lexsort((np.arange(cust.size), cust, ordinal))
    cust, month, ordinal = cust[order], month[order], ordinal[order]
    segment = master.cust_segment[cust]
    n_lines = np.minimum(1 + rng.poisson(np.array(LINES_EXTRA)[segment]), MAX_LINES)
    # Distinct SKUs per order: weighted sampling without replacement (Gumbel top-k).
    weights = product_log_weights(master)[master.cust_region[cust], month - 1]
    keys = weights + rng.gumbel(size=weights.shape)
    top = np.argsort(-keys, axis=1, kind="stable")[:, :MAX_LINES]
    take = np.arange(MAX_LINES)[None, :] < n_lines[:, None]
    line_order, line_rank = np.nonzero(take)
    product = top[take]
    lc, lm, lseg = cust[line_order], month[line_order], segment[line_order]
    category = master.prod_category[product]
    quantity = 1 + rng.poisson(np.array(QTY_MEAN)[category] * np.array(QTY_SEGMENT)[lseg] - 1)
    year = (lm - 1) // 12
    list_cents = master.list_cents[year, product]
    cost_cents = master.cost_cents[year, product]
    cal_month = (lm - 1) % 12 + 1
    summer_or_footwear = category != 3
    late_summer = np.isin(cal_month, (8, 9)) & summer_or_footwear
    eligible = late_summer | (np.isin(cal_month, (1, 2)) & (category == 3))
    clearance = eligible & (rng.random(product.size) < CLEARANCE)
    run_out = (lm >= master.prod_last[product] - 1) & (lm <= master.prod_last[product])
    noise = rng.normal(0.0, 0.015, product.size)
    rate = (
        np.array(DISCOUNT_SEGMENT)[lseg]
        + 0.06 * master.cust_distributor[lc]
        + 0.03 * (quantity >= 24)
        + 0.10 * clearance
        + 0.15 * run_out
        + noise
    )
    d4 = np.rint(np.clip(rate, 0.0, 0.35) * 10_000).astype(np.int64)
    # NetAmount = Quantity x UnitListPrice x (1 - DiscountRate), half up to the cent, in integers.
    net = (quantity * list_cents * (10_000 - d4) * 2 + 10_000) // 20_000
    return {
        "order": line_order,
        "line": line_rank + 1,
        "customer": lc,
        "month": lm,
        "ordinal": ordinal[line_order],
        "product": product,
        "rep": master.cust_rep[lc],
        "quantity": quantity,
        "list_cents": list_cents,
        "cost_cents": cost_cents,
        "d4": d4,
        "net_cents": net,
    }


def region_month_revenue(master: Master, lines: dict[str, np.ndarray]) -> np.ndarray:
    out = np.zeros((len(REGIONS), SIM_MONTHS), dtype=np.int64)
    np.add.at(out, (master.cust_region[lines["customer"]], lines["month"] - 1), lines["net_cents"])
    return out


def build_targets(master: Master) -> list[dict[str, object]]:
    total = np.zeros((len(REGIONS), SIM_MONTHS), dtype=np.int64)
    for seed in TARGET_SEEDS:
        total += region_month_revenue(master, simulate(np.random.default_rng(seed), master))
    rows: list[dict[str, object]] = []
    for m in range(1, SIM_MONTHS + 1):
        for ri, region in enumerate(REGIONS):
            mean_eur = total[ri, m - 1] / len(TARGET_SEEDS) / 100
            target = math.floor(mean_eur * region.ambition / 1000 + 0.5) * 1000
            month = month_start(m).strftime("%Y-%m")
            rows.append({"Month": month, "RegionCode": region.code, "TargetRevenueEUR": target})
    return rows


# ---------------------------------------------------------------- writers

ORDER_COLUMNS = (
    "OrderNumber",
    "OrderLine",
    "OrderDate",
    "CustomerCode",
    "SKU",
    "SalesRepCode",
    "Quantity",
    "UnitListPriceEUR",
    "DiscountRate",
    "UnitCostEUR",
    "NetAmountEUR",
)
CSV_COLUMNS: dict[str, tuple[str, ...]] = {
    "products.csv": (
        "ProductKey",
        "SKU",
        "ProductName",
        "Category",
        "CategorySort",
        "Subcategory",
        "SubcategorySort",
        "Brand",
        "ListPriceEUR",
        "LaunchDate",
        "DiscontinuedDate",
    ),
    "customers.csv": (
        "CustomerKey",
        "CustomerCode",
        "CustomerName",
        "Segment",
        "Channel",
        "CountryCode",
        "Country",
        "RegionCode",
        "AccountSince",
    ),
    "regions.csv": ("RegionKey", "RegionCode", "Region", "SortOrder"),
    "sales_reps.csv": ("SalesRepKey", "SalesRepCode", "SalesRepName", "Email", "RegionCode"),
    "security.csv": ("UserEmail", "RegionCode"),
    "targets.csv": ("Month", "RegionCode", "TargetRevenueEUR"),
}
NUMBER_FORMATS = {2: "yyyy-mm-dd", 7: "0.00", 8: "0.0000", 9: "0.00", 10: "0.00"}
MODIFIED = re.compile(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)")
EXPORT_STAMP = EXPORT_TIME.strftime("%Y-%m-%dT%H:%M:%SZ").encode("ascii")


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows([row[column] for column in columns] for row in rows)


def export_rows(master: Master, lines: dict[str, np.ndarray]) -> dict[int, list[list[object]]]:
    """Order lines up to the data end, per year, numbered SO-YY-NNNNNN in date order within each year."""
    keep = lines["ordinal"] <= LAST_DAY.toordinal()
    sel = {name: values[keep] for name, values in lines.items()}
    by_year: dict[int, list[list[object]]] = {year: [] for year in YEARS}
    sequence = dict.fromkeys(YEARS, 0)
    current, number = -1, ""
    for i in range(sel["order"].size):
        date = dt.date.fromordinal(int(sel["ordinal"][i]))
        if sel["order"][i] != current:
            current = int(sel["order"][i])
            sequence[date.year] += 1
            number = f"SO-{date.year % 100:02d}-{sequence[date.year]:06d}"
        by_year[date.year].append(
            [
                number,
                int(sel["line"][i]),
                date,
                master.customers[int(sel["customer"][i])]["CustomerCode"],
                master.products[int(sel["product"][i])]["SKU"],
                master.reps[int(sel["rep"][i])]["SalesRepCode"],
                int(sel["quantity"][i]),
                int(sel["list_cents"][i]) / 100,
                int(sel["d4"][i]) / 10_000,
                int(sel["cost_cents"][i]) / 100,
                int(sel["net_cents"][i]) / 100,
            ]
        )
    return by_year


def write_workbook(path: Path, year: int, rows: list[list[object]]) -> None:
    wb = Workbook(write_only=True)
    wb.properties.creator = "Veltrano ERP"
    wb.properties.lastModifiedBy = "Veltrano ERP"
    wb.properties.created = EXPORT_TIME
    wb.properties.modified = EXPORT_TIME
    ws = wb.create_sheet("Orders")
    title = WriteOnlyCell(ws, value=f"Veltrano Outdoor · Order lines export · {year}")
    title.font = Font(bold=True, size=14)
    ws.append([title])
    ws.append(["ERP export, EUR, net of discount"])
    header = []
    for name in ORDER_COLUMNS:
        cell = WriteOnlyCell(ws, value=name)
        cell.font = Font(bold=True)
        header.append(cell)
    ws.append(header)
    for row in rows:
        out: list[object] = []
        for column, value in enumerate(row):
            if column in NUMBER_FORMATS:
                cell = WriteOnlyCell(ws, value=value)
                cell.number_format = NUMBER_FORMATS[column]
                out.append(cell)
            else:
                out.append(value)
        ws.append(out)
    info = wb.create_sheet("Export info")
    end = dt.date(year, 12, 31) if year < LAST_DAY.year else LAST_DAY
    for label, value in (
        ("Period from", dt.date(year, 1, 1)),
        ("Period to", end),
        ("Rows", len(rows)),
        ("Exported at", EXPORT_TIME),
    ):
        cell = WriteOnlyCell(info, value=value)
        if isinstance(value, dt.date):
            cell.number_format = "yyyy-mm-dd hh:mm" if isinstance(value, dt.datetime) else "yyyy-mm-dd"
        info.append([label, cell])
    buffer = io.BytesIO()
    wb.save(buffer)
    # The same bytes on every run: rewrite the archive with a fixed entry time and pin the modified time,
    # which openpyxl sets to the current time while saving.
    stamp = EXPORT_TIME.timetuple()[:6]
    with (
        zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as source,
        zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for item in source.infolist():
            entry = zipfile.ZipInfo(item.filename, date_time=stamp)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            data = source.read(item.filename)
            if item.filename == "docProps/core.xml":
                data = MODIFIED.sub(rb"\g<1>" + EXPORT_STAMP + rb"\g<2>", data)
            target.writestr(entry, data)


def generate(out: Path) -> None:
    rng = np.random.default_rng(SEED)
    master = build_master(rng)
    lines = simulate(rng, master)
    targets = build_targets(master)
    (out / "sales_orders").mkdir(parents=True, exist_ok=True)
    for year, rows in export_rows(master, lines).items():
        write_workbook(out / "sales_orders" / f"sales_orders_{year}.xlsx", year, rows)
    tables = {
        "products.csv": master.products,
        "customers.csv": master.customers,
        "regions.csv": master.regions,
        "sales_reps.csv": master.reps,
        "security.csv": master.security,
        "targets.csv": targets,
    }
    for name, rows in tables.items():
        write_csv(out / name, CSV_COLUMNS[name], rows)


def workbook_values(path: Path) -> dict[str, list[tuple[object, ...]]]:
    wb = load_workbook(path, read_only=True)
    try:
        return {ws.title: [tuple(row) for row in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    finally:
        wb.close()


def compare(expected: Path, actual: Path) -> list[str]:
    problems = []
    for name in CSV_COLUMNS:
        if not (actual / name).exists():
            problems.append(f"{name}: missing")
        elif (actual / name).read_bytes() != (expected / name).read_bytes():
            problems.append(f"{name}: differs from a fresh build")
    for year in YEARS:
        rel = Path("sales_orders") / f"sales_orders_{year}.xlsx"
        if not (actual / rel).exists():
            problems.append(f"{rel.as_posix()}: missing")
        elif workbook_values(actual / rel) != workbook_values(expected / rel):
            problems.append(f"{rel.as_posix()}: sheet names or cell values differ from a fresh build")
    return problems


def shown_path(path: Path) -> str:
    """The path as printed: relative to the repository root when it lies inside it."""
    resolved = path.resolve()
    return resolved.relative_to(ROOT).as_posix() if resolved.is_relative_to(ROOT) else resolved.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Veltrano Outdoor data files (seed 41).")
    parser.add_argument("--out", type=Path, default=ROOT / "data")
    parser.add_argument("--check", action="store_true", help="compare a fresh build with the files in --out")
    args = parser.parse_args(argv)
    shown = shown_path(args.out)
    if not args.check:
        generate(args.out)
        print(f"wrote 3 workbooks and {len(CSV_COLUMNS)} CSV files to {shown}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        generate(Path(tmp))
        problems = compare(Path(tmp), args.out)
    for problem in problems:
        print(f"FAIL {problem}")
    if problems:
        return 1
    print(f"{shown} matches a fresh build (3 workbooks, {len(CSV_COLUMNS)} CSV files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
