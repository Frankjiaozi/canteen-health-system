from decimal import Decimal
from types import SimpleNamespace

from app.modules.nutrition.service import _closure_checks
from app.shared.enums import SeasoningCategory


def test_zero_expected_and_actual_usage_is_not_an_anomaly():
    log = SimpleNamespace(
        oil_total_g=Decimal("0"), salt_total_g=Decimal("0"), sugar_total_g=Decimal("0")
    )
    rows = _closure_checks(log, {})
    assert len(rows) == 3
    assert all(row.status == "ok" and row.deviation == 0 for row in rows)


def test_positive_actual_with_zero_prediction_has_no_invented_ratio():
    log = SimpleNamespace(
        oil_total_g=Decimal("0"), salt_total_g=Decimal("0"), sugar_total_g=Decimal("20")
    )
    rows = _closure_checks(log, {})
    sugar = next(row for row in rows if row.category == SeasoningCategory.SUGAR)
    assert sugar.status == "warn"
    assert sugar.deviation is None
