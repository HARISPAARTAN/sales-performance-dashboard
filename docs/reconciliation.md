# Reconciliation

Every check is computed twice: in Python by `tools/reference.py` (pandas, on the files in `data/`) and in Power BI
Desktop, R01 to R14 by the saved query `pbip/SalesPerformance.SemanticModel/DAXQueries/Reconciliation.dax` and R15
and R16 from the Revenue card on Overview under Modeling, View as, role `Regional manager`
(`docs/desktop-session.md`). `tests/test_measures.py` recomputes the Python column and compares each Desktop value
as soon as it is entered.

Tolerance: amounts ± 0.005 EUR, counts exact, ratios ± 0.00005. The Revenue card shows € m with two decimals
(`€ 1.77 m`) and View as applies to report visuals only, so R15 and R16 (kind `card`) hold the number of millions
the card shows and compare at that precision (± 0.005 m).

Desktop session: not yet run.

| Id | Check | Kind | Python | Desktop |
|---|---|---|---|---|
| R01 | Revenue 2024 | amount | 12197476.84 |  |
| R02 | Revenue 2025 | amount | 10255380.39 |  |
| R03 | Gross margin % 2024 | ratio | 0.352801 |  |
| R04 | Orders 2024 | count | 5284 |  |
| R05 | Average order value 2024 | amount | 2308.38 |  |
| R06 | Discount % 2024 | ratio | 0.115720 |  |
| R07 | Units 2024 Tents | count | 8242 |  |
| R08 | Revenue YoY % 2025 | ratio | 0.065939 |  |
| R09 | Revenue R12 September 2025 | amount | 12831873.59 |  |
| R10 | Revenue PYTD 2025 | amount | 9620983.64 |  |
| R11 | Target 2025 DACH | amount | 5298000.00 |  |
| R12 | Target attainment % 2025 DACH | ratio | 0.992903 |  |
| R13 | Products for 80 % 2024 | count | 64 |  |
| R14 | Order lines | count | 59539 |  |
| R15 | Revenue 2024 as the Nordics manager | card | 1768902.65 |  |
| R16 | Revenue 2024 as the West manager | card | 4227491.88 |  |

The Python column is the output of `uv run python tools/reference.py`. The Nordics manager is the address in
`data/security.csv` with the region `NRD`; the West manager is the address with `BNL` and `FRA`.
