from typing import Any


class AgentError(Exception):
    def __init__(
        self, message: str, status: int = 422, code: str = "agent_error", details: Any = None
    ):
        self.message, self.status, self.code, self.details = message, status, code, details
        super().__init__(message)

    def body(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class TaskClarification(AgentError):
    """正常的缺失/歧义交互，不作为执行失败，也不隐式放宽用户条件。"""

    def __init__(self, message: str, field: str = "conditions", choices: list[dict] | None = None):
        super().__init__(message, code="clarification_required")
        self.field, self.choices = field, choices or []
        self.parameters: dict | None = None
        self.questions: list[dict] = []
