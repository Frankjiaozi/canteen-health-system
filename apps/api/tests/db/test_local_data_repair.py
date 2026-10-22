from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.db.registry import Base
from app.db.session import get_session_factory
from sqlalchemy import delete, select, text
from tools._repair_snapshots import generate_seed, matching_meals, read_all
from tools.repair_local_data import backup_database, repair, target_url

from tests.helpers import today_local


@pytest.mark.parametrize(("host", "production"), [("db.example.com", False), ("127.0.0.1", True)])
def test_refuses_remote_or_production(host, production):
    settings = SimpleNamespace(
        database_url=f"postgresql+psycopg://user:pass@{host}/anything", is_production=production
    )
    with pytest.raises(RuntimeError, match="仅允许本机"):
        target_url(settings)


def test_target_database_is_fixed():
    settings = SimpleNamespace(
        database_url="postgresql+psycopg://user:pass@localhost/original", is_production=False
    )
    assert target_url(settings).database == "canteen_agent_demo"


def test_missing_backup_tool_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr("tools.repair_local_data.shutil.which", lambda _: None)
    settings = SimpleNamespace(
        database_url="postgresql+psycopg://user:pass@localhost/original", is_production=False
    )
    with pytest.raises(RuntimeError, match="找不到 pg_dump"):
        backup_database(target_url(settings), tmp_path, "unused")
    assert not list(tmp_path.glob("*.dump"))


def test_current_database_is_noop(db_session):
    connection = db_session.connection()
    before = read_all(connection)
    report = repair(connection, before, before, today=today_local())
    assert report["changes"] == {}
    assert report["recomputed_meals"] == 0
    assert read_all(connection) == before


def test_custom_material_value_is_preserved(db_session):
    connection = db_session.connection()
    source = read_all(connection)
    row = source["ingredients"][0]
    table = Base.metadata.tables["ingredients"]
    custom = row["energy_kcal"] + Decimal("17")
    connection.execute(table.update().where(table.c.id == row["id"]).values(energy_kcal=custom))
    report = repair(connection, source, source, today=today_local())
    assert (
        connection.execute(select(table.c.energy_kcal).where(table.c.id == row["id"])).scalar_one()
        == custom
    )
    assert any(item["id"] == str(row["id"]) for item in report["skipped"])


def test_recognized_reference_updates_but_keeps_price_and_note(db_session):
    connection = db_session.connection()
    source = read_all(connection)
    old = deepcopy(source)
    row = old["ingredients"][0]
    row["energy_kcal"] -= Decimal("5")
    table = Base.metadata.tables["ingredients"]
    connection.execute(
        table.update()
        .where(table.c.id == row["id"])
        .values(energy_kcal=row["energy_kcal"], unit_price=Decimal("99"), note="人工采购记录")
    )
    report = repair(connection, source, old, today=today_local())
    actual = connection.execute(select(table).where(table.c.id == row["id"])).mappings().one()
    assert report["changes"]["updated_ingredients"] == 1
    assert actual["energy_kcal"] == source["ingredients"][0]["energy_kcal"]
    assert actual["unit_price"] == 99 and actual["note"] == "人工采购记录"


def test_changed_recipe_snapshot_prevents_history_replacement(db_session):
    source = read_all(db_session.connection())
    actual = deepcopy(source)
    item = actual["daily_log_items"][0]
    log = next(row for row in actual["daily_logs"] if row["id"] == item["daily_log_id"])
    key = (log["date"], log["meal_type"])
    assert key in matching_meals(actual, source)
    item["recipe_snapshot"]["ingredients"][0]["quantity_per_serving_g"] = "999"
    assert key not in matching_meals(actual, source)


def test_missing_meal_can_be_repaired_then_rolled_back(db_session, monkeypatch):
    connection = db_session.connection()
    source = read_all(connection)
    menu = next(
        row
        for row in source["menu_days"]
        if row["date"] == today_local() - timedelta(days=1) and row["meal_type"] == "BREAKFAST"
    )
    log = next(
        row
        for row in source["daily_logs"]
        if row["date"] == menu["date"] and row["meal_type"] == menu["meal_type"]
    )
    tables = Base.metadata.tables
    connection.execute(
        delete(tables["dish_nutritions"]).where(
            tables["dish_nutritions"].c.date == menu["date"],
            tables["dish_nutritions"].c.meal_type == menu["meal_type"],
        )
    )
    connection.execute(delete(tables["menu_days"]).where(tables["menu_days"].c.id == menu["id"]))
    connection.execute(delete(tables["daily_logs"]).where(tables["daily_logs"].c.id == log["id"]))
    before = read_all(connection)
    savepoint = connection.begin_nested()
    report = repair(connection, source, source, today=today_local())
    assert report["changes"]["added_menu_days"] == 1
    assert report["changes"]["added_daily_logs"] == 1
    assert report["candidates"]["BREAKFAST"] > 0
    savepoint.rollback()
    assert read_all(connection) == before

    # A failure after inserts must also roll the whole attempted repair back.
    def failed_compute(*args, **kwargs):
        raise RuntimeError("injected computation failure")

    with monkeypatch.context() as patch:
        patch.setattr("tools.repair_local_data.compute_menu_day", failed_compute)
        with pytest.raises(RuntimeError, match="injected"), connection.begin_nested():
            repair(connection, source, source, today=today_local())
    assert read_all(connection) == before


def test_confirmed_history_refresh_retires_only_obsolete_derived_rows(db_session):
    connection = db_session.connection()
    before = read_all(connection)
    source = deepcopy(before)
    menu = source["menu_days"][0]
    source["menu_days"] = [menu]
    removed = next(row for row in source["menu_day_items"] if row["menu_day_id"] == menu["id"])
    source["menu_day_items"].remove(removed)
    log = next(
        row
        for row in source["daily_logs"]
        if row["date"] == menu["date"] and row["meal_type"] == menu["meal_type"]
    )
    source["daily_log_items"] = [
        row
        for row in source["daily_log_items"]
        if not (row["daily_log_id"] == log["id"] and row["dish_id"] == removed["dish_id"])
    ]
    report = repair(connection, source, before, refresh_history=True, today=today_local())
    assert report["changes"]["upgraded_seed_meals"] == 1
    assert report["changes"]["retired_obsolete_nutrition_rows"] > 0
    after = read_all(connection)
    assert not any(
        row["date"] == menu["date"]
        and row["meal_type"] == menu["meal_type"]
        and row["dish_id"] == removed["dish_id"]
        for row in after["dish_nutritions"]
    )
    assert after["users"] == before["users"]
    assert after["dishes"] == before["dishes"]
    assert after["recipe_items"] == before["recipe_items"]


def test_seed_generation_leaves_no_schema_or_public_changes(db_session):
    engine = get_session_factory().kw["bind"]
    connection = db_session.connection()
    before = read_all(connection)
    schemas = (
        connection.execute(
            text("select schema_name from information_schema.schemata order by schema_name")
        )
        .scalars()
        .all()
    )
    generated = generate_seed(engine)
    assert len(generated["dishes"]) == 40
    assert read_all(connection) == before
    assert (
        connection.execute(
            text("select schema_name from information_schema.schemata order by schema_name")
        )
        .scalars()
        .all()
        == schemas
    )
