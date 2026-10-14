"""模型元数据的一致性检查（不依赖数据库）。

这些断言把项目里的三条数据层约定固化下来：表清单、UUID 主键、枚举列必须有 CHECK 约束。
"""

from __future__ import annotations

# 必须从注册表导入：Base.metadata 只包含「已被导入过」的模型
from app.db.registry import Base
from sqlalchemy import CheckConstraint
from sqlalchemy import Enum as SAEnum

EXPECTED_TABLES = {
    # 认证与留痕
    "users",
    "audit_logs",
    # 食材与调味料
    "ingredients",
    "seasonings",
    # 菜品与配方
    "dishes",
    "recipe_items",
    "recipe_seasonings",
    # 菜单
    "menu_days",
    "menu_day_items",
    # 每日采集与反馈
    "daily_logs",
    "daily_log_items",
    "feedbacks",
    # 营养结果、校准与基准
    "dish_nutritions",
    "calibration_factors",
    "nutrition_standards",
    # 预测与推荐
    "forecasts",
    "menu_suggestions",
    # 法定节假日日历：预测的修正依据
    "holidays",
}


def test_expected_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_table_has_a_single_column_uuid_primary_key() -> None:
    for table in Base.metadata.tables.values():
        primary_key_columns = list(table.primary_key.columns)
        assert len(primary_key_columns) == 1, f"{table.name} 的主键不是单列"
        assert primary_key_columns[0].name == "id", f"{table.name} 的主键列名不是 id"


def test_every_enum_column_has_a_check_constraint() -> None:
    """枚举列必须同时具备 CHECK 约束，否则数据库层不设防。"""
    for table in Base.metadata.tables.values():
        check_names = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        for column in table.columns:
            if not isinstance(column.type, SAEnum):
                continue
            expected = f"ck_{table.name}_{column.name}_valid"
            assert expected in check_names, f"{table.name}.{column.name} 缺少取值约束 {expected}"


def test_timestamp_columns_are_timezone_aware() -> None:
    """所有时间戳列必须带时区，禁止出现区域无关的 naive datetime。"""
    timestamp_columns = {"created_at", "updated_at", "submitted_at", "decided_at"}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.name not in timestamp_columns:
                continue
            assert getattr(column.type, "timezone", False), (
                f"{table.name}.{column.name} 未使用带时区的类型"
            )
