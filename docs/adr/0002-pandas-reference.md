# ADR 0002: An independent pandas reference in integer cents

Status: accepted (2026-10-29)

## Context

Every headline number of the report must be checked against a computation that does not share code with Power BI. The same numbers feed the reconciliation table, the measure test, the replica's data file and the replica's expected filter states. The reference must read the workbooks without a download on the owner's machine or in CI.

## Decision

`tools/reference.py` uses pandas: it reads the workbooks through openpyxl and the CSV files directly, converts every amount to integer cents (int64) and implements each measure and calculation item of the model as a plain function over a filter context, following the rules of [the measures](../measures.md). One module feeds `tests/test_measures.py`, the Python column of `docs/reconciliation.md`, `tools/build_replica_data.py` and `tests/replica/expected.json`. It is tested on its own against a 14-line fixture whose expected values are worked out in `tests/test_reference.py`.

## Consequences

- Totals are exact: sums of integer cents never round, and the export's `NetAmountEUR` is the only rounded amount.
- The reference and the generator use the same library, pinned by `uv.lock`; nothing is downloaded.
- The DAX and the Python code are written separately, so a shared misunderstanding of a rule would pass both; the worked fixture and the written rules guard against that.

## Alternatives considered

- duckdb: reads xlsx only through an extension fetched on first use, a download on the owner's machine and in CI.
- Recomputing in DAX only: no independent check.
- Floating-point euros: totals of 60,000 lines would differ from Power BI's fixed decimal in the last cent.
