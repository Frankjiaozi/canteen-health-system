"""验证 S01–S06 与当前 Pydantic 契约一致。"""

from typing import Any

from app.modules.menuplan.schemas import (
    MenuPlanResponse,
    PlanReadiness,
    PublishPlanReceipt,
    UndoPlanReceipt,
)
from pydantic import BaseModel, Field

from .samples import S01_NORMAL, S02_NO_HISTORY, S03_MISSING_DATA, S04_ERRORS, S05_PUBLISH, S06_UNDO


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorSample(BaseModel):
    status: int = Field(ge=400, le=599)
    body: ErrorBody


def test_s01_normal_matches_the_response_model() -> None:
    plan = MenuPlanResponse.model_validate(S01_NORMAL)

    assert plan.suggestion_id and plan.snapshot_token
    assert len(plan.snapshot_token) == 64
    assert len(plan.expected_menu_token) == 64
    assert plan.dishes[0].predicted_servings
    assert plan.requirements
    assert plan.total_cost and plan.budget


def test_s02_no_history_has_a_blocking_readiness_and_a_valid_error() -> None:
    readiness = PlanReadiness.model_validate(S02_NO_HISTORY["readiness"])
    error = ErrorSample.model_validate(S02_NO_HISTORY["error"])

    assert readiness.state == "blocked"
    assert any(issue.severity == "blocking" for issue in readiness.issues)
    assert error.status == 422
    assert error.body.code == "business_rule_violated"


def test_s03_missing_price_keeps_known_and_unknown_values_apart() -> None:
    plan = MenuPlanResponse.model_validate(S03_MISSING_DATA)

    assert plan.missing_price_warning
    assert any(row.unit_price is None and row.estimated_cost is None for row in plan.requirements)
    assert any(row.estimated_cost is not None for row in plan.requirements)


def test_s04_error_samples_use_the_unified_envelope() -> None:
    samples = [ErrorSample.model_validate(row) for row in S04_ERRORS]

    assert {row.status for row in samples} == {422, 403, 404}
    assert all(row.body.code in {"validation_error", "forbidden", "not_found"} for row in samples)


def test_s05_publish_and_conflict_samples() -> None:
    success = PublishPlanReceipt.model_validate(S05_PUBLISH["success"])
    repeat = PublishPlanReceipt.model_validate(S05_PUBLISH["repeat"])
    conflicts = [ErrorSample.model_validate(row) for row in S05_PUBLISH["conflicts"]]

    assert success.already_published is False
    assert repeat.already_published is True
    assert all(row.status == 409 and row.body.code == "conflict" for row in conflicts)


def test_s06_undo_and_conflict_samples() -> None:
    success = UndoPlanReceipt.model_validate(S06_UNDO["success"])
    conflicts = [ErrorSample.model_validate(row) for row in S06_UNDO["conflicts"]]

    assert success.meal_type_label == "午餐"
    assert all(row.status == 409 for row in conflicts)
