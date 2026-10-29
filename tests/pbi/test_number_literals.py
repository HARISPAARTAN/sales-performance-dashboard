"""Decimal literals in the generated PBIR never use exponent notation (a threshold of one million stays "1000000D")."""

import json

import pytest

import build_report
import pbir

pytestmark = pytest.mark.pbi


@pytest.mark.parametrize(
    ("value", "literal"),
    [(0, "0D"), (1, "1D"), (0.9, "0.9D"), (1.1, "1.1D"), (1_000_000, "1000000D"), (1234567.5, "1234567.5D")],
)
def test_number_literal(value, literal):
    assert build_report._number(value) == literal


def test_comparison_filter_literal_has_no_exponent():
    spec = {"field": ["_Measures", "Revenue"], "kind": "Measure", "op": ">=", "value": 2_500_000}
    text = json.dumps(pbir._comparison_filter("f0", spec))
    assert "2500000D" in text and "e+" not in text
