# ADR 0004: Dynamic row-level security through a disconnected table

Status: accepted (2026-10-29)

## Context

The brief asks that regional managers see only their own regions. There are four managers for five regions: one covers Benelux and France. A role per region would need a change to the model whenever a manager changes, and a manager with two regions would need two roles.

## Decision

The table `Security` (from `data/security.csv`: one row per sign-in address and region, five rows) is hidden and has no relationship. The role `Regional manager` filters `Security` to `USERPRINCIPALNAME()` and filters `DimRegion`, `DimCustomer` and `DimSalesRep` with `RegionKey IN CALCULATETABLE(VALUES(Security[RegionKey]), Security[User e-mail] = USERPRINCIPALNAME())`. `DimRegion` filters both facts; the customer and rep filters keep other regions' names out of slicers and tables. `Target` blanks itself when `DimCustomer` or `DimSalesRep` is filtered; whether the role filters on those tables count as such a filter is checked in the Desktop session (step 8 of `../desktop-session.md`), and the measure is reworked if the target tiles are blank for a role member.

## Consequences

- A new manager is one more row in `security.csv` and a refresh, not a model change ([handover](../handover.md#adding-a-regional-manager)).
- A sign-in address without a row sees no data.
- The reconciliation reads the role through View as in Desktop (R15 and R16); the replica, a public page, has no role.
- Publish to web cannot use a model with a role; `tools/pbi/make_public_variant.py` builds a copy without the role and the `Security` table.

## Alternatives considered

- One static role per region: a model change for every staffing change.
- A relationship from `Security` to `DimRegion` with filtering in both directions: a second filter path and a hidden many-to-many in the model.
