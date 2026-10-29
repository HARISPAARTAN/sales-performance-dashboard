"""Umbrella section 8: docs/reconciliation.md holds R01-R16; its Python column equals tools/reference.py, and every
Desktop value, once entered, matches within the tolerance of spec section 10."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

import reference

DOC = Path(__file__).resolve().parents[1] / "docs" / "reconciliation.md"
ROW = re.compile(r"^\| (R\d\d) \| ([^|]+?) \| (amount|count|ratio|card) \| ([^|]+?) \| ([^|]*?) *\|$", re.M)
SESSION = re.compile(r"^Desktop session: (.+)$", re.M)
CARDS = {"R15", "R16"}


def rows() -> list[tuple[str, str, str, str, str]]:
    return ROW.findall(DOC.read_text(encoding="utf-8"))


def matches(kind: str, value: object, desktop: str) -> bool:
    """value as tools/reference.py returns it (amounts in cents); desktop as read in Desktop."""
    shown = Decimal(desktop.replace(",", ""))
    if kind == "amount":
        return abs(shown - Decimal(str(value)) / 100) <= Decimal("0.005")
    if kind == "card":
        return abs(shown - Decimal(str(value)) / 100_000_000) <= Decimal("0.005")
    if kind == "count":
        return shown == Decimal(int(value))  # type: ignore[call-overload]
    return abs(float(shown) - float(value)) <= 0.00005  # type: ignore[arg-type]


def test_the_table_lists_r01_to_r16():
    assert [r[0] for r in rows()] == [f"R{n:02d}" for n in range(1, 17)]


def test_python_column_equals_the_reference(model):
    expected = reference.reconciliation(model)
    for (rid, label, kind, python, _), (eid, elabel, value, ekind) in zip(rows(), expected, strict=True):
        assert (rid, label) == (eid, elabel)
        assert kind == ("card" if rid in CARDS else ekind), rid
        assert python == reference.display(value, ekind), rid


def test_desktop_values_match_within_the_tolerance(model):
    expected = {rid: value for rid, _, value, _ in reference.reconciliation(model)}
    entered = [(rid, kind, desktop) for rid, _, kind, _, desktop in rows() if desktop.strip()]
    if not entered:
        pytest.skip("no Desktop values yet (docs/desktop-session.md)")
    assert not SESSION.search(DOC.read_text(encoding="utf-8")).group(1).startswith("not yet"), "date the session"
    bad = [(rid, desktop) for rid, kind, desktop in entered if not matches(kind, expected[rid], desktop.strip())]
    assert not bad, bad


@pytest.mark.parametrize(
    ("kind", "value", "desktop", "ok"),
    [
        ("amount", 1219747684, "12197476.840000", True),
        ("amount", 1219747684, "12197476.846000", False),
        ("count", 5284, "5284.000000", True),
        ("count", 5284, "5285.000000", False),
        ("ratio", 0.352801, "0.352850", True),
        ("ratio", 0.352801, "0.352900", False),
        ("card", 176890265, "1.77", True),
        ("card", 176890265, "1.76", False),
    ],
)
def test_tolerance_rules(kind, value, desktop, ok):
    assert matches(kind, value, desktop) is ok
