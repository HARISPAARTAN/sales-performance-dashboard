# Handover

Notes for the person who refreshes or changes the dashboard. Commands run from the repository root with uv; the Power BI steps need Power BI Desktop on Windows.

## Set up

```bash
uv sync
uv run python tools/make_data.py --check          # the committed data equal a fresh build
uv run pytest -q                                   # every offline test; the TOM test skips without build/tom
```

Open `pbip\SalesPerformance.pbip` in Power BI Desktop. Home, Transform data, Edit parameters: `DataFolder` must name this clone's `data\` folder with the trailing backslash (the default is `E:\GITGUB\sales-performance-dashboard\data\`). OK, Apply changes, then Refresh. No credentials are involved: every source is a local file.

The optional TOM parse test needs Microsoft's Tabular Object Model assemblies and pythonnet:

```bash
uv sync --group pbi
uv run python tools/pbi/copy_tom.py --from <folder with the six Microsoft.AnalysisServices DLLs>
uv run --group pbi pytest tests/pbi/test_tmdl_tom.py -q
```

## Refresh

Home, Refresh. The model reads the three workbooks from `data\sales_orders\` and the CSV files from `data\`. After a refresh, the reconciliation query (DAX query view, tab `Reconciliation`, Run) must still match the Python column of `docs/reconciliation.md` when the data files are unchanged.

## Adding a year's export

1. Save the ERP export as `data/sales_orders/sales_orders_<year>.xlsx` with the same layout: sheet `Orders`, two title rows, the header in row 3 with the columns of [the data model](data-model.md#files). The folder query picks up every `sales_orders_*.xlsx`; nothing changes in Power Query.
2. Extend `EndDate` (Edit parameters) to the 31 December of the new year, so `DimDate` covers it; `StartDate` stays a 1 January.
3. Add the new months to `data/targets.csv` (next section).
4. Refresh. `Is past` follows the last order date by itself, so YTD, PY and R12 move with the data.
5. For this demo the files are generated: change `LAST_DAY`, `SIM_MONTHS` and `EXPORT_MONTHS` in `tools/make_data.py`, run `uv run python tools/make_data.py`, then `uv run python tools/build_replica_data.py`, and update the bands in `tests/test_make_data.py` and the values in `docs/reconciliation.md` from the new run.

## Changing targets

`data/targets.csv` holds one row per month and region: `Month` (`2026-01`), `RegionCode` (`DACH`, `BNL`, `NRD`, `FRA`, `IBE`), `TargetRevenueEUR` in whole euros. Edit or add rows and refresh; the report shows the target from the first month that has one. `Target` is blank under a product, customer or sales-rep filter, because targets exist per region and month only.

## Adding a regional manager

Add one row per region to `data/security.csv`: the manager's sign-in address (`UserEmail`, as Power BI reports it through `USERPRINCIPALNAME()`) and the `RegionCode`. A manager for two regions has two rows. Refresh; no model change is needed. Check it in Desktop: Modeling, View as, Other user = the new address, tick `Regional manager`, OK; the Overview page shows only the manager's regions. An address without a row sees no data.

In the Power BI service the role needs members: on the semantic model, More options, Security, role `Regional manager`, add the managers or a group. Workspace members with edit rights see all data regardless of the role.

## Building the role-free copy

Publish to web cannot use a model with row-level security. The public variant drops the role and the `Security` table and keeps everything else:

```bash
uv run python tools/pbi/make_public_variant.py
```

It writes `build/public/SalesPerformance (public).pbip` with its model and report folders and a `README.txt`; `build/` is git-ignored. Open that copy in Desktop, refresh, and publish it, never the project under `pbip/`. Publishing is not part of this repository's scope.

## Changing the report

Until the first save in Power BI Desktop, the report is generated: edit `tools/pbi/pages.json` (or `tools/pbi/build_report.py`), run `uv run python tools/pbi/build_report.py` and `uv run pytest tests/pbi -q`. After the first save, the files Desktop wrote are the source: change the report in Desktop or in the PBIR files directly, and do not run `build_report.py` again; it would overwrite Desktop's files ([desktop session](desktop-session.md)). The lint tests keep running on the saved files.

The model is edited in the TMDL files under `pbip/SalesPerformance.SemanticModel/definition/` or in Desktop. A changed measure changes `docs/measures.md` too (`tests/test_docs.py` compares the DAX) and, when its rule changes, `tools/reference.py` and the replica's `web/assets/js/model.js`.

## Changing the theme

The theme `Veltrano Dark` is generated from the kit's dark tokens: `uv run python tools/pbi/build_theme.py` writes `pbip/SalesPerformance.Report/StaticResources/RegisteredResources/veltrano-dark.json`; `--check` compares the content with a fresh build. After the kit is updated (next section), run it again and check the contrast with `uv run pytest tests/pbi/test_theme.py -q`.

## Updating portfolio-kit or ECharts

- Kit: with a newer tag in the local clone `E:\GITGUB\portfolio-kit`, run `uv run python tools/sync_kit.py --tag <tag>`, then `uv run python tools/sync_kit.py --check`, change the tag in `.github/workflows/ci.yml` (job `kit`), and run `node tools/checks/contrast.mjs` and the screenshots.
- ECharts: `web/vendor/echarts.min.js` is version 5.6.0 (Apache-2.0, licence in `web/vendor/LICENSE-echarts.txt`). A new version is a new download with its SHA-256 recorded in the commit message; the chart options live in `web/assets/js/charts.js`, and `tests/replica/charts.test.mjs` and the screenshots show what changed.

## Updating Faker or numpy

Updating Faker changes the person names: regenerate the data and the replica data (`uv run python tools/make_data.py`, then `uv run python tools/build_replica_data.py`). Dependabot ignores Faker and numpy feature releases for that reason.

## Checks before a push

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
uv run python tools/make_data.py --check
uv run python tools/build_replica_data.py --check
node --test "tests/replica/*.test.mjs"
node tools/checks/contrast.mjs
uv run python tools/check_page_weight.py
OFFLINE=1 node tools/checks/verify-site.mjs
uv run python tools/checks/scrub.py
PLAYWRIGHT_FROM=<package.json of a folder with playwright> OUT=<folder outside the repository> node tools/checks/shots.mjs
```

`shots.mjs` serves `web/` on 127.0.0.1, opens every tab at 1440 and 390 px in both themes with the installed Chrome, and fails on any external request, console error or sideways scrolling; the screenshots go to `OUT`.
