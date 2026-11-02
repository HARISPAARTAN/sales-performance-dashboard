# Changelog

All notable changes to this project are listed here.

## v0.1.0 (2026-11-02)

- Seeded generator for the data of the fictional wholesaler Veltrano Outdoor: three yearly order workbooks (59,539 order lines from January 2023 to September 2025) and six CSV files; `--check` compares a fresh build with the committed files.
- Power BI project (PBIP): a TMDL model with a star schema, 22 measures, the calculation group `Time intelligence` with seven items on month-index windows, the field parameter `Analyse by` and the role `Regional manager` with dynamic row-level security; a PBIR report with eight pages, synced slicers, reset bookmarks, a tooltip page and the theme `Veltrano Dark` built from the portfolio-kit tokens; the saved DAX query `Reconciliation`.
- An independent pandas reference in integer cents for every measure and calculation item, and the reconciliation table R01 to R16.
- HTML replica on GitHub Pages with six tabs, the report's filters and rules, ECharts 5.6.0 and portfolio-kit v0.1.0; its filter code is tested on twelve filter states against the reference.
- Offline checks of the PBIP: JSON schemas, TMDL and PBIR lint, the reconciliation query, the role-free public variant, the theme's contrast.
- Docs: client brief, data model, measures, architecture, five ADRs, handover notes and the Desktop session.
