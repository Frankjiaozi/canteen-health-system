from datetime import date as Date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class PlanParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on_date: Date
    meal_type: Literal["BREAKFAST", "LUNCH", "DINNER"] = "LUNCH"
    diner_count: int | None = Field(default=None, ge=1, le=100000)
    budget_per_person: Decimal = Field(
        default=Decimal("8"), gt=0, le=1000, max_digits=8, decimal_places=2
    )
    excluded_dish_ids: list[UUID] = Field(default_factory=list, max_length=50)


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2000)
    parameters: PlanParameters
    request_id: UUID
    expected_revision: int = Field(ge=0)


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class ToolTrace(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool: str
    label: str
    status: Literal["running", "success", "error"]
    detail: str = ""


class SuggestedReply(BaseModel):
    label: str = Field(max_length=80)
    content: str = Field(max_length=2000)


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str
    trace: list[ToolTrace] = Field(default_factory=list)
    kind: Literal["message", "clarification", "failure"] = "message"
    clarification_field: str | None = None
    suggestions: list[SuggestedReply] = Field(default_factory=list, max_length=5)


class PlanVersion(BaseModel):
    revision: int
    created_at: str
    parameters: PlanParameters
    result: dict[str, Any]
    publication: dict[str, Any] | None = None
    #: 这次发布被撤回的回执。发布回执本身保留不动，撤回是另一件事——
    #: 把它塞进 publication 里，会让「发布过」和「还生效」混成一个字段。
    undone: dict[str, Any] | None = None
    readiness: dict[str, Any] | None = None
    data_notice: str = ""


class ReviewIssue(BaseModel):
    date: str
    meal_type: str
    meal_label: str
    source: str
    link: str
    kind: str
    title: str
    detail: str
    suggestion: str


class ReviewReport(BaseModel):
    start: str
    end: str
    days: int
    record_count: int
    days_with_records: int
    missing_dates: list[str]
    issues: list[ReviewIssue]
    rows: list[dict[str, Any]]
    truncated: bool
    note: str


class PendingQuestion(BaseModel):
    field: str
    message: str
    choices: list[SuggestedReply] = Field(default_factory=list, max_length=5)


class PendingTask(BaseModel):
    field: str
    parameters: PlanParameters
    intent: str = "generate_menu_plan"
    questions: list[PendingQuestion] = Field(default_factory=list)


class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[ChatMessage] = Field(default_factory=list)
    plans: list[PlanVersion] = Field(default_factory=list)
    review: ReviewReport | None = None
    readiness: dict[str, Any] | None = None
    pending_task: PendingTask | None = None
    completed_requests: list[str] = Field(default_factory=list, exclude=True)
    request_fingerprints: dict[str, str] = Field(default_factory=dict, exclude=True)

    @property
    def revision(self) -> int:
        return len(self.plans)


class ReviewArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=7, ge=1, le=90)


class DishArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: str = Field(default="", max_length=64)


class EmptyArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanParameterPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on_date: Date | None = None
    meal_type: Literal["BREAKFAST", "LUNCH", "DINNER"] | None = None
    diner_count: int | None = Field(default=None, ge=1, le=100000)
    budget_per_person: Decimal | None = Field(
        default=None, gt=0, le=1000, max_digits=8, decimal_places=2
    )
    excluded_dish_ids: list[UUID] | None = Field(default=None, max_length=50)


class ClarificationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=400)
    field: Literal[
        "conditions",
        "on_date",
        "meal_type",
        "diner_count",
        "budget_per_person",
        "excluded_dish_ids",
        "intent",
    ] = "conditions"
    options: list[SuggestedReply] = Field(default_factory=list, max_length=4)
    known_parameters: PlanParameterPatch = Field(
        default_factory=PlanParameterPatch,
        description="只填写用户已经明确改变的条件；未改或不确定字段省略，不得用默认值代替。",
    )


class AgentStatus(BaseModel):
    mode: Literal["rules", "model"]
    model_name: str | None
    data_notice: str
    can_plan: bool
    capabilities: list[str]


class SessionSummary(BaseModel):
    id: str
    title: str
    updated_at: str
    revision: int
