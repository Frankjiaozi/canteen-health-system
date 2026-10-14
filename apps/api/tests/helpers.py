"""测试共用的小工具。"""

from __future__ import annotations

from datetime import date, datetime

from app.core.config import get_settings


def today_local() -> date:
    """应用时区下的今天。

    用例里凡是"今天"都用它，不要写成 `max(日期)`。开发库上除了种子历史，
    还可能留着端到端用例造出来的**未来日期**的菜单与采集记录，
    而"最新的那一天"一旦被它们占住，断言就会指向一个与用例毫不相干的日子——
    报错信息还看不出是这个原因。
    """
    return datetime.now(get_settings().timezone).date()
