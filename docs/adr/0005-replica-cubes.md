# ADR 0005: The replica runs on columnar integer cubes

Status: accepted (2026-10-29)

## Context

The live replica on GitHub Pages must answer the same filters as the report (years, months, regions, categories, a cross-filter, a drill) without a server, within a page weight of 3 MB including ECharts (about 1 MB), and with numbers that equal the report's to the cent. Shipping the 59,539 order lines as JSON would cost several megabytes on its own.

## Decision

`tools/build_replica_data.py` aggregates through `tools/reference.py` into five columnar cubes of integer cents in `web/assets/data/replica.json`: `S` month × country × category × segment × channel (net, gross, cost, units), `P` month × product × region (net, cost, units), `C` month × customer (net, gross, cost, orders), `O` the order list (month, customer, category bit mask) for Orders, Average order value and Active customers, and `T` month × region targets; plus the dimension lists. The budget is 1.3 MB; the fallback, set in advance, drops the region from `P` and tells the Products tab that the region filter does not apply. `web/assets/js/model.js` filters and sums the cubes in pure functions; `tests/replica/model.test.mjs` runs it on twelve filter states whose expected values come from the reference.

## Consequences

- `replica.json` holds about 1.0 MB, so the fallback is not needed; everything under `web/` weighs about 2.3 MB.
- Distinct counts stay exact: orders are counted from the order list, never summed from a cube.
- A filter the cubes cannot answer (for example by brand) is not offered in the replica; the report has the full model.

## Alternatives considered

- The order lines as JSON: several times the budget.
- A WebAssembly database in the browser: several megabytes of runtime for a few aggregations.
- Pre-computed answers per filter state: the combinations of years, months, regions and categories are too many.
