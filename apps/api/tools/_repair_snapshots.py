import subprocess
import sys
import types
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from app.db import seed
from app.db.registry import Base
from sqlalchemy import select, text
from sqlalchemy.orm import Session


def read_all(connection):
    return {
        table.name: [dict(row) for row in connection.execute(select(table)).mappings()]
        for table in Base.metadata.sorted_tables
    }


LEGACY_REF = "c51e43b921dd7946e1e2274d75551ac46070300f"


def generate_seed(engine, *, legacy=False, day=None):
    module = seed
    if legacy:
        try:
            code = subprocess.check_output(
                ["git", "show", LEGACY_REF + ":apps/api/app/db/seed.py"],
                cwd=Path(seed.__file__).resolve().parents[4],
                text=True,
                encoding="utf-8",
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError("缺少旧初始化版本的 Git 历史，请补全仓库历史后重试") from None
        name = "audit_seed_" + LEGACY_REF
        module = types.ModuleType(name)
        module.__file__ = seed.__file__
        sys.modules[name] = module
        exec(compile(code, seed.__file__, "exec"), module.__dict__)
    previous_datetime = module.datetime
    if day:

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.combine(day, datetime.min.time(), tzinfo=tz)

        module.datetime = FrozenDatetime
    try:
        with engine.connect() as connection:
            holidays = [
                dict(row)
                for row in connection.execute(select(Base.metadata.tables["holidays"])).mappings()
            ]
            connection.rollback()
            transaction = connection.begin()
            schema = "seed_audit_" + uuid4().hex
            connection.execute(text(f"CREATE SCHEMA {schema}"))
            connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            Base.metadata.create_all(connection)
            if holidays and not hasattr(module, "seed_holidays"):
                connection.execute(Base.metadata.tables["holidays"].insert(), holidays)
            with Session(bind=connection) as session:
                module.run(session)
            if not transaction.is_active:
                raise RuntimeError("初始化源事务意外结束，停止修复")
            result = read_all(connection)
            transaction.rollback()
            return result
    finally:
        module.datetime = previous_datetime


def comparable(row):
    return {
        key: value
        for key, value in row.items()
        if key not in {"created_at", "updated_at", "recipe_snapshot"}
    }


def snapshot_matches(row, source):
    """Do not overwrite a migrated snapshot whose actual recipe was edited."""
    snapshot = row.get("recipe_snapshot")
    if snapshot is None:
        return True
    dish_id = row["dish_id"]
    dish = next((item for item in source["dishes"] if item["id"] == dish_id), None)
    if dish is None:
        return False
    seasonings = {item["id"]: item for item in source["seasonings"]}
    expected = {
        "cooking_method": dish["cooking_method"],
        "ingredients": [
            {
                "ingredient_id": str(item["ingredient_id"]),
                "quantity_per_serving_g": str(item["quantity_per_serving_g"]),
                "edible_ratio_override": None
                if item["edible_ratio_override"] is None
                else str(item["edible_ratio_override"]),
            }
            for item in source["recipe_items"]
            if item["dish_id"] == dish_id
        ],
        "seasonings": [
            {
                "seasoning_id": str(item["seasoning_id"]),
                "category": seasonings[item["seasoning_id"]]["category"],
                "quantity_per_serving_g": str(item["quantity_per_serving_g"]),
            }
            for item in source["recipe_seasonings"]
            if item["dish_id"] == dish_id
        ],
    }

    def normalize(value):
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items() if k != "recipe_version"}
        if isinstance(value, list):
            return sorted(
                (normalize(item) for item in value),
                key=lambda item: str(item.get("ingredient_id", item.get("seasoning_id", ""))),
            )
        if isinstance(value, str):
            try:
                return Decimal(value)
            except InvalidOperation:
                return value
        return value

    return normalize(snapshot) == normalize(expected)


def matching_meals(actual, source):
    result = []
    for log in actual["daily_logs"]:
        other = next((row for row in source["daily_logs"] if row["id"] == log["id"]), None)
        if other is None or comparable(log) != comparable(other):
            continue
        menus = [
            row
            for row in actual["menu_days"]
            if row["date"] == log["date"] and row["meal_type"] == log["meal_type"]
        ]
        if len(menus) != 1:
            continue
        menu = menus[0]
        seed_menu = next((row for row in source["menu_days"] if row["id"] == menu["id"]), None)
        if seed_menu is None or comparable(menu) != comparable(seed_menu):
            continue
        matching = True
        for name, fk, parent in [
            ("daily_log_items", "daily_log_id", log["id"]),
            ("menu_day_items", "menu_day_id", menu["id"]),
        ]:
            left = {row["id"]: comparable(row) for row in actual[name] if row[fk] == parent}
            right = {row["id"]: comparable(row) for row in source[name] if row[fk] == parent}
            if left != right:
                matching = False
        if matching:
            rows = [row for row in actual["daily_log_items"] if row["daily_log_id"] == log["id"]]
            if all(snapshot_matches(row, source) for row in rows):
                result.append((log["date"], log["meal_type"]))
    return result
