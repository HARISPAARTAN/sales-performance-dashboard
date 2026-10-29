# Power BI Desktop session

The one validation session in Power BI Desktop, about 30 minutes. The owner works in Desktop; the assistant only reads the screen (screen captures with `tools/checks/capture_screen.ps1`) and never clicks or types in Desktop. Any credentials dialog is the owner's alone; this project reads local files only, so none is expected.

## Before the session

- Every offline test is green: `uv run pytest -q` (the TOM parse test with `uv run --group pbi pytest tests/pbi/test_tmdl_tom.py -q` after `tools/pbi/copy_tom.py`).
- No Desktop cache exists: `find pbip -name cache.abf` prints nothing.
- The report equals its source: `uv run python tools/pbi/build_report.py` followed by `git status --short pbip` prints nothing.
- The Python column of `docs/reconciliation.md` is filled and `tests/test_measures.py` passes.

## Source of the report

- **Until the first save in Desktop**, `tools/pbi/pages.json` and `tools/pbi/build_report.py` generate the report files (pages, visuals, bookmarks, `report.json`); a fix to the report goes there and the files are generated again. The TMDL files are edited directly.
- **After the first save**, the files Desktop wrote are the source. `build_report.py` is not run again: it would overwrite Desktop's normalisation and every fix made in the session. The lint tests keep running on the saved files.

## Steps

1. Close all Desktop windows. Open `E:\GITGUB\sales-performance-dashboard\pbip\SalesPerformance.pbip`. If Desktop asks for the preview features `Power BI Project (.pbip) save option` and `Store semantic model using TMDL format`: File, Options and settings, Options, Preview features, tick both, OK, restart Desktop and open the project again.
2. An error dialog (for example "Unable to open document", "TMDL Format Error" or a PBIR schema error with a file name): copy its text unchanged to the assistant and close Desktop without saving. The error loop below applies.
3. Home, Transform data, Edit parameters: `DataFolder` must name the clone's `data\` folder with a trailing backslash (`E:\GITGUB\sales-performance-dashboard\data\`). OK, Apply changes, then Home, Refresh. No credentials are involved; if a privacy-level dialog appears, set both sources to Organizational. Every table loads; a table that fails: its error text to the assistant.
4. Model view: seven relationships are drawn (`FactSales` to the five dimensions, `FactTargets` to `DimDate` and `DimRegion`); `DimDate`, Table tools: Mark as date table is set on `Date`; the calculation group `Time intelligence` and the field parameter `Analyse by` are listed in the Data pane.
5. DAX query view (fourth icon on the left), tab `Reconciliation`, Run. If the tab is missing, open `pbip\SalesPerformance.SemanticModel\DAXQueries\Reconciliation.dax` in Notepad, copy everything, paste it into a new query tab and Run. Say "Desktop is open"; the assistant captures the result grid (14 rows, R01 to R14) and fills the Desktop column of `docs/reconciliation.md`. A mismatch is fixed in the DAX first and run again; screenshots come after.
6. Report view, the default state of every page (Reset first if a slicer moved). On request, open Overview, Trends, Products (the pointer resting on a Pareto bar, so the product tooltip shows), Regions, Customers, Targets and Info, then the model view; the assistant captures each.
7. Interactions, each captured: on Overview, Analyse by set to Region; on Products, drill down on the category bar (the drill buttons in the visual header, then a click on Tents); on Regions, a click on a region bar; Ctrl+click on Reset on each of these pages.
8. Row-level security: Modeling, View as, Other user = the Nordics manager's address from `data/security.csv` (the row with `NRD`), tick `Regional manager`, OK. Set Year to 2024 on Overview; the assistant reads the Revenue card (R15). Still viewing as the Nordics manager, open Targets and say whether the target tiles show values or are blank (this checks that the role filters do not make `ISFILTERED` in `Target` true). Repeat with the West manager (the address with the rows `BNL` and `FRA`; R16). Stop viewing.
9. File, Save; close Desktop. The assistant reviews the diff, runs the offline tests again and commits the files, the screenshots and the table.

## What to check on the pages

Expected tiles on Overview in the default state (Year 2025): Revenue `€ 10.26 m` with `+6.6 %`, Gross margin % `34.7 %` with `-0.4 pp`, Orders `4,302` with `+2.2 %`, Average order value `€ 2,384` with `+4.3 %`, Discount % `11.6 %` with `+0.0 pp`. No visual may show "Can't display the visual" or a red error icon; otherwise "See details" and the text to the assistant.

Some formatting objects are written from the published schemas but only Desktop shows whether it applies them. Each has a fallback in Desktop; a fallback used is noted for the commit message.

| Check | Expected | Fallback in Desktop |
|---|---|---|
| PY lines | dashed and muted, Current in the accent (Overview, Trends) | Format, Lines, series PY, Line style Dashed |
| Pareto chart | 40 bars sorted by revenue, the cumulative line on a secondary axis from 0 to 100 % | Filters pane, Product, Top N 40 by Revenue; Format, Y axis, Secondary, range 0 to 1 |
| Products table | data bars on Revenue | Format, Cell elements, Revenue, Data bars on |
| Attainment bars (Targets) | ok colour at 100 % and above, warning colour below, a constant line at 100 % | Format, Bars, Color, fx, Rules; Analytics pane, Constant line, value 1 |
| Attainment matrix (Targets) | background from warning (90 %) over the surface (100 %) to ok (110 %) | Format, Cell elements, Background color, fx, Gradient with a middle colour |
| KPI tiles | the value card above the `vs PY` card, nothing cut off | resize the two cards inside the tile |
| Category bar (Products) | drill buttons in the header; drilling down shows subcategories, the breadcrumb back works | Format, Visual header, Drill icons on |
| Analyse by slicer | tiles, single select, Category selected by default | Format, Slicer settings, Style Tile, Single select on |
| Slicer row | Year lists 2023 to 2025 only, 2025 selected; Months is a slider from 1 to 12; Targets has the note instead of Category | Year: Filters pane, Revenue is not blank |
| Sync groups | a region chosen on Overview is chosen on Regions, Customers and Targets too | View, Sync slicers, tick the pages for the group |
| Reset buttons | Ctrl+click restores Year 2025, clears the other slicers, Analyse by Category, the drill at the top | set the slicers, Bookmarks pane, the page's bookmark, Update |
| Cross-filter | a click on a region bar filters the other visuals (not highlight) | Format, Edit interactions, Filter |
| Product tooltip | a pointer on a Pareto bar or a table row shows the tooltip page with the product's name, four cards and a monthly line | Format, Tooltips, Type Report page, Page Product tooltip |

## Error loop

Applies until the first save in Desktop, while `build_report.py` is still the source.

1. The owner passes on Desktop's error text unchanged.
2. The assistant finds the file and the line and fixes the cause: `tools/pbi/pages.json` or `tools/pbi/build_report.py` for report files, then generates them again; the TMDL files directly for the model. Generated report files are never edited by hand. Once Desktop has saved the report, the saved PBIR file is fixed directly instead.
3. The assistant runs `uv run pytest tests/pbi -q` and the TOM test, and adds a regression check to the matching lint test when the kind of error is new.
4. The owner opens the project again (or chooses "Apply external changes" in Desktop's notification bar) and continues where it failed. After three rounds without progress on the same error, the session stops and the error texts are reported.

## After the session (assistant)

1. `git status`: no `.pbi/` file may be staged (`localSettings.json`, `cache.abf`, `editorSettings.json` and `unappliedChanges.json` are git-ignored); another one that appears belongs in `.gitignore`, not in the commit. New `.platform` files from Desktop are committed.
2. Review `git diff pbip`: only formatting and Desktop metadata may change (line endings, property order, `lineageTag`s, the linguistic metadata in `cultures/en-US.tmdl`, `diagramLayout.json`, the theme files as formatted JSON, newer `$schema` versions). Any change of content (a renamed object, a removed visual, changed DAX, a changed data type) is a finding to explain in the commit message.
3. Run the offline tests on the saved files. If Desktop wrote a `$schema` version that is not vendored, add its URL to `unpublished` in `tools/pbi/schema_versions.json` (the schema test skips those files); vendoring the newer schema is a separate step with its own download approval. Adapt a lint test only to the formatting, never weaken what it checks.
4. Copy the screenshots of `docs/screenshots/SHOTLIST.md` into `docs/screenshots/`, fill the Desktop column of `docs/reconciliation.md` (with the session date), and commit with `chore(pbi): files as saved by Power BI Desktop; screenshots and reconciliation`.
