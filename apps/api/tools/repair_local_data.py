"""本机独立开发库增量修复：默认预演，--apply 备份并校验后提交。

pnpm data:repair [--legacy-seed-date YYYY-MM-DD] [--apply]
只补缺失数据、更新可确认的旧初始化值；不用于生产数据库。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.core.config import Settings
from app.db.registry import Base
from app.modules.forecast.repository import load_dish_history
from app.modules.nutrition.service import compute_menu_day
from app.modules.recommendation.service import candidate_dish_ids
from app.shared.enums import MealType
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from tools._repair_snapshots import generate_seed, matching_meals, read_all

API_DIR = Path(__file__).resolve().parents[1]
TARGET_DATABASE = "canteen_agent_demo"
PROVENANCE = "本地开发初始化数据，来源 main 内置种子；非真实经营记录"


def target_url(settings):
    url = make_url(settings.database_url)
    if settings.is_production or url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("仅允许本机非生产环境；不会连接远程或生产数据库")
    return url.set(database=TARGET_DATABASE)


def backup_database(url, directory, container):
    """Backup must succeed before mutation. Passwords never enter command arguments."""
    directory.mkdir(parents=True, exist_ok=True)
    backup = directory / f"before-{uuid4().hex}.dump"
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    dump = shutil.which("pg_dump")
    if dump:
        command = [
            dump,
            "-h",
            url.host,
            "-p",
            str(url.port or 5432),
            "-U",
            url.username,
            "-d",
            url.database,
            "-Fc",
        ]
    else:
        if not shutil.which("docker"):
            raise RuntimeError("找不到 pg_dump 或 Docker，未写入数据；请先安装备份工具")
        ports = subprocess.run(
            ["docker", "port", container, "5432/tcp"], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        if not any(line.endswith(":" + str(url.port or 5432)) for line in ports):
            raise RuntimeError("PostgreSQL 容器映射端口与目标不符，拒绝备份和修复")
        command = [
            "docker",
            "exec",
            "--env",
            "PGPASSWORD",
            container,
            "pg_dump",
            "-U",
            url.username,
            "-d",
            url.database,
            "-Fc",
        ]
    with backup.open("xb") as stream:
        subprocess.run(command, env=env, stdout=stream, stderr=subprocess.PIPE, check=True)
    with backup.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise RuntimeError("备份格式校验失败，未写入数据")
    return backup


def repair(connection, source, old, *, refresh_history=False, today):
    """Run within the caller's transaction; never commit here."""
    tables = Base.metadata.tables
    before = read_all(connection)
    allowed = {}
    counts = Counter()
    skipped = []
    recompute = set()
    matched = set(matching_meals(before, old)) if refresh_history else set()

    def allow(name, row_id):
        allowed.setdefault(name, set()).add(row_id)

    def update(name, row_id, values):
        connection.execute(
            tables[name].update().where(tables[name].c.id == row_id).values(**values)
        )
        allow(name, row_id)

    def insert(name, row):
        connection.execute(tables[name].insert().values(**row))
        counts["added_" + name] += 1

    new_dishes = set()
    for name, natural in [
        ("ingredients", "name"),
        ("seasonings", "name"),
        ("dishes", "name"),
        ("nutrition_standards", "code"),
    ]:
        known = {r["id"]: r for r in before[name]}
        natural_ids = {r[natural]: r["id"] for r in before[name]}
        for row in source[name]:
            if row["id"] in known:
                continue
            if row[natural] in natural_ids:
                raise RuntimeError(f"{name} 存在同名但不同 ID 的记录，请人工核对；事务将回滚")
            insert(name, row)
            if name == "dishes":
                new_dishes.add(row["id"])
    for name in ["recipe_items", "recipe_seasonings"]:
        for row in source[name]:
            if row["dish_id"] in new_dishes:
                insert(name, row)

    for name in ["ingredients", "seasonings"]:
        previous = {r["id"]: r for r in old[name]}
        latest = {r["id"]: r for r in source[name]}
        fields = ["energy_kcal", "protein_g", "fat_g", "carb_g", "sodium_mg"]
        if name == "ingredients":
            fields += ["edible_ratio"]
        for row in before[name]:
            prior, new = previous.get(row["id"]), latest.get(row["id"])
            if prior is None or new is None:
                continue
            if all(row[k] == new[k] for k in [*fields, "data_source", "source_version"]):
                continue
            recognized = (
                all(row[k] == prior[k] for k in fields)
                and row["data_source"] in {prior["data_source"], "人工录入参考值，待核对"}
                and row["source_version"] in {prior["source_version"], "未核对"}
            )
            if not recognized:
                skipped.append(
                    {
                        "table": name,
                        "id": str(row["id"]),
                        "reason": "与旧初始化值不一致，保留人工数据",
                    }
                )
                continue
            values = {
                k: new[k] for k in [*fields, "data_source", "source_version"] if row[k] != new[k]
            }
            if row.get("note") == prior.get("note") and row.get("note") != new.get("note"):
                values["note"] = new["note"]
            if values:
                update(name, row["id"], values)
                counts["updated_" + name] += 1

    occupied = {
        (r["date"], r["meal_type"])
        for name in ["menu_days", "daily_logs", "dish_nutritions"]
        for r in before[name]
    }
    menus = {(r["date"], r["meal_type"]): r for r in before["menu_days"]}
    logs = {(r["date"], r["meal_type"]): r for r in before["daily_logs"]}
    latest_logs = {(r["date"], r["meal_type"]): r for r in source["daily_logs"]}
    user_ids = {r["id"] for r in before["users"]}
    for menu in source["menu_days"]:
        key = (menu["date"], menu["meal_type"])
        if key in occupied and key not in matched:
            continue
        log = latest_logs[key]
        if menu["created_by"] not in user_ids or log["submitted_by"] not in user_ids:
            raise RuntimeError("缺少原初始化账号，不自动创建账号或重置口令；请先核对初始化环境")
        if key in matched:
            measured = any(
                (r["date"], r["meal_type"]) == key and r["value_type"] != "THEORETICAL"
                for r in before["dish_nutritions"]
            )
            referenced = any(
                r.get("daily_log_id") == logs[key]["id"] for r in before.get("feedbacks", [])
            )
            if measured or referenced:
                skipped.append(
                    {
                        "date": str(key[0]),
                        "meal": str(key[1]),
                        "reason": "包含实测、校准或反馈，保留",
                    }
                )
                continue
            menu_id, log_id = menus[key]["id"], logs[key]["id"]
            served = {
                r["dish_id"] for r in source["menu_day_items"] if r["menu_day_id"] == menu["id"]
            }
            for row in before["dish_nutritions"]:
                if (row["date"], row["meal_type"]) == key and row["dish_id"] not in served:
                    connection.execute(
                        delete(tables["dish_nutritions"]).where(
                            tables["dish_nutritions"].c.id == row["id"]
                        )
                    )
                    allow("dish_nutritions", row["id"])
                    counts["retired_obsolete_nutrition_rows"] += 1
            for name, fk, parent_id in [
                ("menu_day_items", "menu_day_id", menu_id),
                ("daily_log_items", "daily_log_id", log_id),
            ]:
                for row in before[name]:
                    if row[fk] == parent_id:
                        allow(name, row["id"])
                connection.execute(delete(tables[name]).where(tables[name].c[fk] == parent_id))
            for name, target, new in [
                ("menu_days", menus[key], menu),
                ("daily_logs", logs[key], log),
            ]:
                values = {
                    k: v for k, v in new.items() if k not in {"id", "created_at", "updated_at"}
                }
                update(name, target["id"], {**values, "note": PROVENANCE})
            counts["upgraded_seed_meals"] += 1
        else:
            insert("menu_days", {**menu, "note": PROVENANCE})
            insert("daily_logs", {**log, "note": PROVENANCE})
            menu_id, log_id = menu["id"], log["id"]
        for row in source["menu_day_items"]:
            if row["menu_day_id"] == menu["id"]:
                insert("menu_day_items", {**row, "menu_day_id": menu_id})
        for row in source["daily_log_items"]:
            if row["daily_log_id"] == log["id"]:
                insert("daily_log_items", {**row, "daily_log_id": log_id, "note": PROVENANCE})
        recompute.add(key)

    if counts:
        recompute |= {
            (r["date"], r["meal_type"]) for r in before["daily_logs"] if r["note"] == PROVENANCE
        }
        for row in before["dish_nutritions"]:
            if (row["date"], row["meal_type"]) in recompute and row["value_type"] == "THEORETICAL":
                allow("dish_nutritions", row["id"])
    with Session(bind=connection) as session:
        for day, meal in sorted(recompute):
            compute_menu_day(session, on_date=day, meal_type=MealType(meal))
        session.flush()
        tomorrow = today + timedelta(days=1)
        candidates = {
            meal.value: len(candidate_dish_ids(session, on_date=tomorrow, meal_type=meal))
            for meal in MealType
        }
        history = load_dish_history(
            session, start=tomorrow - timedelta(weeks=8), end=today, meal_type=MealType.LUNCH
        )
        low_history = {str(k): len(v) for k, v in history.items() if len(v) < 3}
    after = read_all(connection)
    preserved = 0
    for name, rows in before.items():
        current = {r["id"]: r for r in after[name]}
        for row in rows:
            if row["id"] in allowed.get(name, set()):
                continue
            if current.get(row["id"]) != row:
                raise RuntimeError(f"发现计划外数据变动：{name}；事务将回滚")
            preserved += 1
    return {
        "changes": dict(counts),
        "matched_old_seed_meals": len(matched),
        "recomputed_meals": len(recompute),
        "other_rows_preserved": preserved,
        "candidates": candidates,
        "lunch_under_three_samples": low_history,
        "skipped": skipped,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="备份后提交；默认只预演并回滚")
    parser.add_argument(
        "--legacy-seed-date",
        type=date.fromisoformat,
        help="旧初始化实际执行日；不填则保留全部已有餐次",
    )
    parser.add_argument("--backup-dir", type=Path, default=API_DIR / "data" / "repair-backups")
    parser.add_argument("--postgres-container", default="canteen-postgres-dev")
    args = parser.parse_args(argv)
    settings = Settings()
    url = target_url(settings)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            actual = MigrationContext.configure(connection).get_current_revision()
            expected = ScriptDirectory.from_config(
                Config(str(API_DIR / "alembic.ini"))
            ).get_current_head()
            if actual != expected:
                raise RuntimeError("独立开发库迁移未完成，请先执行 pnpm demo:prepare")
        today = datetime.now(settings.timezone).date()
        source = generate_seed(engine)
        old = generate_seed(engine, legacy=True, day=args.legacy_seed_date or today)
        backup = None
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            names = ",".join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
            connection.execute(text(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE"))
            if args.apply:
                backup = backup_database(url, args.backup_dir, args.postgres_container)
            report = repair(
                connection,
                source,
                old,
                refresh_history=args.legacy_seed_date is not None,
                today=today,
            )
            report.update(
                {
                    "applied": args.apply,
                    "database": url.database,
                    "backup": str(backup) if backup else None,
                }
            )
            if args.apply:
                transaction.commit()
            else:
                transaction.rollback()
        args.backup_dir.mkdir(parents=True, exist_ok=True)
        report_path = args.backup_dir / f"report-{uuid4().hex}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"报告：{report_path}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(
            str(error)
            if isinstance(error, RuntimeError)
            else "外部备份或 Git 命令失败，未提交修复；请检查工具与容器配置"
        ) from None
