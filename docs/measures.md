# Measures

Every measure lives in the table `_Measures` of `pbip/SalesPerformance.SemanticModel` with a description, a display
folder and a format string. The DAX below is the TMDL's, character for character apart from indentation;
`tests/test_docs.py` compares the two. Amounts are in EUR; "€ amount" is the dynamic format string

```dax
VAR v = ABS(SELECTEDMEASURE()) RETURN IF(v >= 1E6, "€ #,0.00,,"" m""", IF(v >= 1E4, "€ #,0.0,"" k""", "€ #,0"))
```

which shows `€ 12.20 m`, `€ 512.3 k` or `€ 2,308`. Rules that every measure follows (spec section 7):

- Comparisons use whole months and only months with sales (`DimDate[Is past]`), so the partial year 2025 compares
  January to September with January to September 2024.
- YoY and YoY % are blank unless every selected month has a previous-year month in the data (none for 2023).
- R12 starts in December 2023; percentages compare in percentage points.
- Text, rank and Pareto measures are blank under every calculation item except Current.
- `Target` is blank under a product, customer or sales-rep filter: targets exist per region and month only.

## Sales

### Revenue

Net revenue after discount, EUR: the sum of NetAmountEUR from the ERP export.

Folder `Sales` · format € amount (dynamic)

```dax
SUM(FactSales[Net amount])
```

### Gross sales

List value before discount, EUR: quantity x list price.

Folder `Sales` · format € amount (dynamic)

```dax
SUM(FactSales[Gross amount])
```

### Cost

Cost of goods sold, EUR: quantity x unit cost.

Folder `Sales` · format € amount (dynamic)

```dax
SUM(FactSales[Cost amount])
```

### Gross margin

Revenue minus cost, EUR.

Folder `Sales` · format € amount (dynamic)

```dax
[Revenue] - [Cost]
```

### Gross margin %

Gross margin as a share of revenue.

Folder `Sales` · format `0.0 %`

```dax
DIVIDE([Gross margin], [Revenue])
```

### Discount %

Discount granted as a share of the list value.

Folder `Sales` · format `0.0 %`

```dax
DIVIDE([Gross sales] - [Revenue], [Gross sales])
```

### Units

Units sold.

Folder `Sales` · format `#,0`

```dax
SUM(FactSales[Quantity])
```

### Orders

Distinct orders; an order counts once if any of its lines is in the filter context.

Folder `Sales` · format `#,0`

```dax
DISTINCTCOUNT(FactSales[Order number])
```

### Average order value

Revenue per order, EUR.

Folder `Sales` · format `€ #,0`

```dax
DIVIDE([Revenue], [Orders])
```

### Active customers

Customers with at least one order line.

Folder `Sales` · format `#,0`

```dax
DISTINCTCOUNT(FactSales[CustomerKey])
```

## Targets

### Target

Revenue target, EUR. Targets exist per region and month only, so the measure is blank under a product, customer or sales-rep filter.

Folder `Targets` · format € amount (dynamic)

```dax
IF(
    ISFILTERED(DimProduct) || ISFILTERED(DimCustomer) || ISFILTERED(DimSalesRep),
    BLANK(),
    SUM(FactTargets[Target revenue])
)
```

### Target to date

Target of the months with sales data (Is past), EUR.

Folder `Targets` · format € amount (dynamic)

```dax
CALCULATE([Target], DimDate[Is past] = TRUE())
```

### Target attainment %

Revenue as a share of the target to date.

Folder `Targets` · format `0.0 %`

```dax
DIVIDE([Revenue], [Target to date])
```

### Target gap

Revenue minus target to date, EUR; negative when behind target.

Folder `Targets` · format € amount (dynamic)

```dax
IF(NOT ISBLANK([Target to date]), [Revenue] - [Target to date])
```

## Products

### Product rank

Revenue rank of one product among the products in the outer filters (ties share a rank, SKIP); blank unless one product is in context.

Folder `Products` · format `0`

```dax
VAR rev = [Revenue]
RETURN
    IF(
        HASONEVALUE(DimProduct[Product]) && NOT ISBLANK(rev),
        CALCULATE(
            RANKX(VALUES(DimProduct[Product]), [Revenue], rev, DESC, SKIP),
            REMOVEFILTERS(DimProduct[Product], DimProduct[SKU]),
            ALLSELECTED(DimProduct[Category])
        )
    )
```

### Pareto cumulative %

Share of revenue held by this product and every product with at least its revenue (ties share a value).

Folder `Products` · format `0.0 %`

```dax
VAR rev = [Revenue]
VAR products =
    CALCULATETABLE(
        ADDCOLUMNS(VALUES(DimProduct[Product]), "@rev", [Revenue]),
        REMOVEFILTERS(DimProduct[Product], DimProduct[SKU]),
        ALLSELECTED(DimProduct[Category])
    )
RETURN
    IF(
        HASONEVALUE(DimProduct[Product]) && NOT ISBLANK(rev),
        DIVIDE(SUMX(FILTER(products, [@rev] >= rev), [@rev]), SUMX(products, [@rev]))
    )
```

### Pareto class

A up to 80 % cumulative revenue, B up to 95 %, C above.

Folder `Products` · format none (text)

```dax
VAR c = [Pareto cumulative %] RETURN IF(NOT ISBLANK(c), IF(c <= 0.8, "A", IF(c <= 0.95, "B", "C")))
```

### Products for 80 %

Number of products whose cumulative revenue stays within 80 % of the total.

Folder `Products` · format `#,0`

```dax
VAR products =
    CALCULATETABLE(
        ADDCOLUMNS(VALUES(DimProduct[Product]), "@rev", [Revenue]),
        REMOVEFILTERS(DimProduct[Product], DimProduct[SKU]),
        ALLSELECTED(DimProduct[Category])
    )
VAR total = SUMX(products, [@rev])
VAR withCum =
    ADDCOLUMNS(
        FILTER(products, [@rev] > 0),
        "@cum", VAR r = [@rev] RETURN SUMX(FILTER(products, [@rev] >= r), [@rev])
    )
RETURN
    COUNTROWS(FILTER(withCum, [@cum] <= 0.8 * total))
```

### Selected product

The product in context, for the product tooltip; blank for several.

Folder `Products` · format none (text)

```dax
SELECTEDVALUE(DimProduct[Product])
```

## Info

### Last sales date

Date of the latest order line in the model, independent of filters.

Folder `Info` · format `d mmm yyyy`

```dax
CALCULATE(MAX(FactSales[Order date]), REMOVEFILTERS())
```

### Data until

Header text: the latest order date in English whatever the viewer's locale.

Folder `Info` · format none (text)

```dax
"Data until " & FORMAT([Last sales date], "d mmm yyyy", "en-US")
```

### Order lines

Number of order lines loaded.

Folder `Info` · format `#,0`

```dax
COUNTROWS(FactSales)
```

## Calculation group Time intelligence

Table `Time intelligence`, column `Time calculation`, precedence 10. Every item except Current starts with the
same variables (`past`, `last`, `guard`, `pct`, `full`, `cur`, `py`); `last - MOD(last - 1, 12)` is the January
of the last month's year because `StartDate` is a 1 January. The month-index windows avoid leap-day shifts.

### Current

The measure as filtered.

```dax
SELECTEDMEASURE()
```

### PY

The same months one year earlier (month index - 12), months with sales only.

```dax
VAR past = CALCULATETABLE(VALUES(DimDate[Month index]), DimDate[Is past] = TRUE())
VAR last = MAXX(past, DimDate[Month index])
VAR guard =
    ISEMPTY(past)
        || ISSELECTEDMEASURE([Product rank], [Pareto cumulative %], [Pareto class], [Products for 80 %],
            [Last sales date], [Data until], [Selected product])
VAR pct = ISSELECTEDMEASURE([Gross margin %], [Discount %], [Target attainment %])
VAR full = MINX(past, DimDate[Month index]) > 12
VAR cur = CALCULATE(SELECTEDMEASURE(), DimDate[Is past] = TRUE())
VAR py =
    CALCULATE(
        SELECTEDMEASURE(),
        REMOVEFILTERS(DimDate),
        TREATAS(SELECTCOLUMNS(past, "@m", DimDate[Month index] - 12), DimDate[Month index])
    )
RETURN
    IF(NOT guard, py)
```

### YoY

Change against PY: the difference for amounts and counts, percentage points for percentages; blank without a full previous year.

Format string: `IF(ISSELECTEDMEASURE([Gross margin %], [Discount %], [Target attainment %]), "+0.0"" pp"";-0.0"" pp"";0.0"" pp""", SELECTEDMEASUREFORMATSTRING())`

```dax
VAR past = CALCULATETABLE(VALUES(DimDate[Month index]), DimDate[Is past] = TRUE())
VAR last = MAXX(past, DimDate[Month index])
VAR guard =
    ISEMPTY(past)
        || ISSELECTEDMEASURE([Product rank], [Pareto cumulative %], [Pareto class], [Products for 80 %],
            [Last sales date], [Data until], [Selected product])
VAR pct = ISSELECTEDMEASURE([Gross margin %], [Discount %], [Target attainment %])
VAR full = MINX(past, DimDate[Month index]) > 12
VAR cur = CALCULATE(SELECTEDMEASURE(), DimDate[Is past] = TRUE())
VAR py =
    CALCULATE(
        SELECTEDMEASURE(),
        REMOVEFILTERS(DimDate),
        TREATAS(SELECTCOLUMNS(past, "@m", DimDate[Month index] - 12), DimDate[Month index])
    )
RETURN
    IF(NOT guard && full && NOT ISBLANK(cur) && NOT ISBLANK(py), IF(pct, (cur - py) * 100, cur - py))
```

### YoY %

Relative change against PY for amounts and counts; blank for percentages and without a full previous year.

Format string: `"+0.0 %;-0.0 %;0.0 %"`

```dax
VAR past = CALCULATETABLE(VALUES(DimDate[Month index]), DimDate[Is past] = TRUE())
VAR last = MAXX(past, DimDate[Month index])
VAR guard =
    ISEMPTY(past)
        || ISSELECTEDMEASURE([Product rank], [Pareto cumulative %], [Pareto class], [Products for 80 %],
            [Last sales date], [Data until], [Selected product])
VAR pct = ISSELECTEDMEASURE([Gross margin %], [Discount %], [Target attainment %])
VAR full = MINX(past, DimDate[Month index]) > 12
VAR cur = CALCULATE(SELECTEDMEASURE(), DimDate[Is past] = TRUE())
VAR py =
    CALCULATE(
        SELECTEDMEASURE(),
        REMOVEFILTERS(DimDate),
        TREATAS(SELECTCOLUMNS(past, "@m", DimDate[Month index] - 12), DimDate[Month index])
    )
RETURN
    IF(NOT guard && NOT pct && full, DIVIDE(cur - py, py))
```

### YTD

From January of the last month with sales in the selection to that month.

```dax
VAR past = CALCULATETABLE(VALUES(DimDate[Month index]), DimDate[Is past] = TRUE())
VAR last = MAXX(past, DimDate[Month index])
VAR guard =
    ISEMPTY(past)
        || ISSELECTEDMEASURE([Product rank], [Pareto cumulative %], [Pareto class], [Products for 80 %],
            [Last sales date], [Data until], [Selected product])
VAR pct = ISSELECTEDMEASURE([Gross margin %], [Discount %], [Target attainment %])
VAR full = MINX(past, DimDate[Month index]) > 12
VAR cur = CALCULATE(SELECTEDMEASURE(), DimDate[Is past] = TRUE())
VAR py =
    CALCULATE(
        SELECTEDMEASURE(),
        REMOVEFILTERS(DimDate),
        TREATAS(SELECTCOLUMNS(past, "@m", DimDate[Month index] - 12), DimDate[Month index])
    )
RETURN
    IF(
        NOT guard,
        CALCULATE(
            SELECTEDMEASURE(),
            REMOVEFILTERS(DimDate),
            DimDate[Month index] >= last - MOD(last - 1, 12),
            DimDate[Month index] <= last
        )
    )
```

### PYTD

YTD one year earlier.

```dax
VAR past = CALCULATETABLE(VALUES(DimDate[Month index]), DimDate[Is past] = TRUE())
VAR last = MAXX(past, DimDate[Month index])
VAR guard =
    ISEMPTY(past)
        || ISSELECTEDMEASURE([Product rank], [Pareto cumulative %], [Pareto class], [Products for 80 %],
            [Last sales date], [Data until], [Selected product])
VAR pct = ISSELECTEDMEASURE([Gross margin %], [Discount %], [Target attainment %])
VAR full = MINX(past, DimDate[Month index]) > 12
VAR cur = CALCULATE(SELECTEDMEASURE(), DimDate[Is past] = TRUE())
VAR py =
    CALCULATE(
        SELECTEDMEASURE(),
        REMOVEFILTERS(DimDate),
        TREATAS(SELECTCOLUMNS(past, "@m", DimDate[Month index] - 12), DimDate[Month index])
    )
RETURN
    IF(
        NOT guard,
        CALCULATE(
            SELECTEDMEASURE(),
            REMOVEFILTERS(DimDate),
            DimDate[Month index] >= last - 12 - MOD(last - 1, 12),
            DimDate[Month index] <= last - 12
        )
    )
```

### R12

The twelve months up to the last month with sales in the selection; from December 2023.

```dax
VAR past = CALCULATETABLE(VALUES(DimDate[Month index]), DimDate[Is past] = TRUE())
VAR last = MAXX(past, DimDate[Month index])
VAR guard =
    ISEMPTY(past)
        || ISSELECTEDMEASURE([Product rank], [Pareto cumulative %], [Pareto class], [Products for 80 %],
            [Last sales date], [Data until], [Selected product])
VAR pct = ISSELECTEDMEASURE([Gross margin %], [Discount %], [Target attainment %])
VAR full = MINX(past, DimDate[Month index]) > 12
VAR cur = CALCULATE(SELECTEDMEASURE(), DimDate[Is past] = TRUE())
VAR py =
    CALCULATE(
        SELECTEDMEASURE(),
        REMOVEFILTERS(DimDate),
        TREATAS(SELECTCOLUMNS(past, "@m", DimDate[Month index] - 12), DimDate[Month index])
    )
RETURN
    IF(
        NOT guard && last >= 12,
        CALCULATE(
            SELECTEDMEASURE(),
            REMOVEFILTERS(DimDate),
            DimDate[Month index] >= last - 11,
            DimDate[Month index] <= last
        )
    )
```

## Field parameter Analyse by

A calculated table read by the slicer `Analyse by` on Overview; the bar chart next to it shows the chosen column.
The replica's segmented control does the same in `web/assets/js/model.js`.

```dax
{
("Category", NAMEOF('DimProduct'[Category]), 0),
("Region", NAMEOF('DimRegion'[Region]), 1),
("Segment", NAMEOF('DimCustomer'[Segment]), 2),
("Channel", NAMEOF('DimCustomer'[Channel]), 3)
}
```

## Role Regional manager

Regional managers see only the regions listed for their sign-in address in Security. Model permission `read`. Whether the role filters on `DimCustomer` and `DimSalesRep` make `ISFILTERED` in `Target` true is
checked in the Desktop session (`desktop-session.md`, step 8); a blank target tile for a role member means the measure is reworked. A sign-in address without a row in `Security` sees no data.

### Filter on Security

```dax
Security[User e-mail] = USERPRINCIPALNAME()
```

### Filter on DimRegion

```dax
DimRegion[RegionKey] IN CALCULATETABLE(VALUES(Security[RegionKey]), Security[User e-mail] = USERPRINCIPALNAME())
```

### Filter on DimCustomer

```dax
DimCustomer[RegionKey] IN CALCULATETABLE(VALUES(Security[RegionKey]), Security[User e-mail] = USERPRINCIPALNAME())
```

### Filter on DimSalesRep

```dax
DimSalesRep[RegionKey] IN CALCULATETABLE(VALUES(Security[RegionKey]), Security[User e-mail] = USERPRINCIPALNAME())
```
