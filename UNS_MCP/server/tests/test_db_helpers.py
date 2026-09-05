"""Pure-Python tests for db.py's helpers -- no database required, so these
run even when SILVER_DATABASE_URL/SEED_DATABASE_URL are unset."""
from decimal import Decimal

from app.db import _to_float


def test_to_float_turns_decimal_into_a_real_float():
    # Postgres NUMERIC arrives as Decimal, which the MCP SDK serializes as a
    # JSON string ("1203.5") rather than the number the spec documents.
    result = _to_float(Decimal("1203.5"))
    assert isinstance(result, float)
    assert result == 1203.5


def test_to_float_passes_none_through():
    assert _to_float(None) is None
    assert _to_float(None, ndigits=4) is None


def test_to_float_rounds_repeating_decimals_when_asked():
    # SQL avg() over integers yields noise like 1119.6666666666666667.
    assert _to_float(Decimal("1119.6666666666666667"), ndigits=4) == 1119.6667


def test_to_float_does_not_round_by_default():
    assert _to_float(Decimal("1119.6666666666666667")) == float("1119.6666666666666667")
