# ADR 0001: Yearly order workbooks combined from a folder

Status: accepted (2026-10-29)

## Context

The client exports the order lines from the ERP to Excel every month. About 60,000 lines over 33 months in one workbook would exceed the 2 MB limit for committed files, and a single file would not show the folder combine that a real monthly export needs. The ERP puts two title rows above the header, and the export already carries the net amount per line.

## Decision

The generator writes one workbook per year (`data/sales_orders/sales_orders_2023.xlsx` to `_2025.xlsx`), each with the sheet `Orders` (two title rows, the header in row 3) and the sheet `Export info`. Power Query reads them with `Folder.Files(DataFolder & "sales_orders")`, keeps only `sales_orders_*.xlsx`, skips the title rows, promotes the header and combines the tables. `NetAmountEUR` stays in the export (rounded half up to the cent by the ERP), so Power BI and Python add up the same cents.

## Consequences

- Each workbook stays well below 2 MB, and a new year's export is one more file in the folder ([handover](../handover.md#adding-a-years-export)).
- The title rows give Power Query a real cleaning step; a change of the export layout breaks one step, not the whole query.
- Workbooks are not byte-reproducible (zip entry times), so `make_data.py --check` compares them by sheet names and cell values, and their properties carry a fixed export time.

## Alternatives considered

- One workbook: over the 2 MB limit.
- CSV instead of Excel: not what the ERP of the brief produces, and it would hide the cleaning step.
- One workbook per month: 33 files for no gain in the demo; the folder combine is the same.
