# Client brief

## The job post (2022)

> We are an outdoor-equipment wholesaler in Innsbruck and sell tents, sleeping gear, backpacks, apparel, footwear and cooking gear to about 400 retailers in Europe. Each month we export our order lines from the ERP to Excel, and sales keeps monthly revenue targets per region in a CSV file. We want an interactive Power BI dashboard on these two sources: revenue and margin, the monthly trend against last year, which products carry the business, how each region sells and where we stand against target. Our regional managers should see only their own regions.

Rebuilt from memory as a demo. The original client's name and data are not used.

Veltrano Outdoor is a fictional company. Every customer, product, person and number in this repository comes from the seeded generator `tools/make_data.py`; e-mail addresses use the reserved domain `veltrano.example`.

## Users and roles

| User | Uses | Access |
|---|---|---|
| Managing director, head of sales | all pages, all regions | the full model (workspace members, outside the role) |
| Regional managers: four people for five regions (one covers Benelux and France) | Overview, Regions, Customers, Targets | role `Regional manager` through the `Security` table |
| Category management (purchasing) | Products, Trends | the full model |
| Sales reps (12) | appear as data in `DimSalesRep` and on the Customers page; not report users in this brief | none |
| Replica visitors | the six tabs of the HTML replica | the public Pages site, no login |

## Scope

In scope:

- the generator and the committed data files (three yearly order workbooks, six CSV files);
- the Power BI project (PBIP): a TMDL model with a star schema, a time-intelligence calculation group, a field parameter and dynamic row-level security; a PBIR report with eight pages; the theme `Veltrano Dark`; a saved DAX query for the reconciliation;
- an independent computation of every headline number in Python (`tools/reference.py`) and the reconciliation table;
- the HTML replica on GitHub Pages, built from the same reference;
- tests, CI, documentation, decision records and one validation session in Power BI Desktop;
- release v0.1.0 and a card on the portfolio site.

Out of scope: Publish to web and any deployment to the Power BI service (`tools/pbi/make_public_variant.py` already builds the role-free copy that Publish to web would need); scheduled or incremental refresh and dataflows; returns and credit notes (the export has none); currencies other than EUR; addresses, cities and map visuals; forecasts and product-level budgets; a mobile layout of the report; Q&A, smart narratives and other generated visuals; paginated reports; third-party visuals.

## Acceptance criteria

1. `tools/make_data.py --check` is clean, the data files are committed and every band of the generator holds ([data model](data-model.md#generator)).
2. CI is green on `main`; Pages serves https://harispaartan.github.io/sales-performance-dashboard/.
3. The PBIP opens, refreshes and renders every visual in Power BI Desktop without an error; the files Desktop saves are committed after a review of the diff.
4. The sixteen checks R01 to R16 of [the reconciliation](reconciliation.md) match between Python and Desktop.
5. Screenshots of the seven report pages, the model and the replica sit in both READMEs; the Status sections claim only verified facts.
6. The local checks pass: scrub, links, contrast, screenshots at 1440 and 390 px without external requests or console errors, page weight at most 3 MB.
7. Release v0.1.0 with a changelog entry, an annotated tag and a GitHub Release.
8. The card on the portfolio site.
