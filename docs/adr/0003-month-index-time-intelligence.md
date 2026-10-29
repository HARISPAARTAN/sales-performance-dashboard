# ADR 0003: Time intelligence on month-index windows

Status: accepted (2026-10-29)

## Context

The data ends on 30 September 2025, so 2025 is a partial year. Comparisons with the previous year must be like for like (January to September against January to September), percentages must compare in percentage points, and a year without a previous year in the data (2023) must not show a growth figure. Built-in functions such as `SAMEPERIODLASTYEAR` and `DATESYTD` shift by dates, which brings leap-day effects (February 2024 has orders on the 29th) and compares a partial year with a full one.

## Decision

`DimDate` carries `Month index` (2023-01 = 1 to 2025-12 = 36) and the calculated column `Is past` (`DimDate[Date] <= MAX(FactSales[Order date])`, without `CALCULATE`, so without context transition or a circular dependency). The calculation group `Time intelligence` (precedence 10) has seven items: Current, PY, YoY, YoY %, YTD, PYTD and R12. Every item except Current works on the selected months that have sales: PY reads the same month indexes minus 12; YoY and YoY % are blank unless every selected month has a previous-year month in the data; YTD and PYTD run from the January of the last selected month; R12 is the twelve months up to the last selected month (from December 2023). Percentages return the difference in points (`+0.4 pp`). Text, rank and Pareto measures are blank under every item except Current. The replica's `model.js` implements the same rules and is tested against the pandas reference.

## Consequences

- Partial years compare like for like, and growth is never shown against a missing year.
- One calculation group replaces seven variants of each measure; the KPI tiles bind the base measure with a visual filter on the item.
- `StartDate` must be a 1 January, because the month index counts from it; `tests/pbi/test_tmdl_lint.py` checks that.

## Alternatives considered

- `SAMEPERIODLASTYEAR`, `DATESYTD`: date shifts, leap days, and a partial year compared with a full one.
- One measure per comparison: about 140 measures for 22 base measures, each a chance to drift.
