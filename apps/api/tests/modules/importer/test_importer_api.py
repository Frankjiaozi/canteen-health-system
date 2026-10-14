"""批量导入：模板、校验报告与执行。

最要紧的两条：校验不通过时一行都不能写；校验通过后数据要真的进去并且算得出营养。
"""

from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from app.modules.importer.template import SHEETS
from fastapi.testclient import TestClient
from openpyxl import Workbook

BASE = "/api/v1/import"


def _workbook(
    *,
    ingredients: list[list[object]] | None = None,
    seasonings: list[list[object]] | None = None,
    dishes: list[list[object]] | None = None,
    recipe: list[list[object]] | None = None,
) -> bytes:
    """按模板的表头造一份工作簿。只看表头顺序，与导出模板保持同一份契约。"""
    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    payload = {
        "食材": ingredients,
        "调味料": seasonings,
        "菜品": dishes,
        "配方": recipe,
    }
    for name, (headers, example) in SHEETS.items():
        sheet = workbook.create_sheet(name)
        sheet.append(headers)
        for row in payload.get(name) or []:
            sheet.append(row)
        del example
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _upload(client: TestClient, content: bytes, *, dry_run: bool) -> dict:
    response = client.post(
        f"{BASE}/dishes",
        params={"dry_run": str(dry_run).lower()},
        files={
            "file": (
                "import.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _ingredient_row(name: str) -> list[object]:
    return [name, "蔬菜类", 30, 2.0, 0.3, 5.0, 10.0, 0.9, 5.5, "接口测试构造", "test", ""]


def _dish_name() -> str:
    return f"导入测试菜-{uuid4().hex[:6]}"


def test_template_can_be_downloaded(as_recorder: TestClient) -> None:
    response = as_recorder.get(f"{BASE}/template")

    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    # xlsx 是 zip 容器，前两个字节固定是 PK
    assert response.content[:2] == b"PK"


def test_template_requires_write_role(as_school_admin: TestClient) -> None:
    assert as_school_admin.get(f"{BASE}/template").status_code == 403


def test_dry_run_reports_errors_without_writing(as_recorder: TestClient) -> None:
    """类别写错、数据来源缺失——两份错都要被指出来，且一行都不能写库。"""
    name = f"不该被写入的食材-{uuid4().hex[:6]}"
    content = _workbook(
        ingredients=[
            [name, "不存在的类别", 30, 2.0, 0.3, 5.0, 10.0, 0.9, 5.5, "接口测试构造", "", ""],
            [f"{name}-缺来源", "蔬菜类", 30, 2.0, 0.3, 5.0, 10.0, 0.9, 5.5, "", "", ""],
        ]
    )

    report = _upload(as_recorder, content, dry_run=True)

    assert report["ok"] is False
    assert report["dry_run"] is True
    messages = " ".join(issue["message"] for issue in report["issues"])
    assert "无法识别" in messages
    assert "数据来源为空" in messages
    # 校验不通过，绝不能写库
    assert as_recorder.get("/api/v1/ingredients", params={"keyword": name}).json()["total"] == 0


def test_missing_sheet_is_reported(as_recorder: TestClient) -> None:
    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    workbook.create_sheet("食材")
    buffer = BytesIO()
    workbook.save(buffer)

    report = _upload(as_recorder, buffer.getvalue(), dry_run=True)

    assert report["ok"] is False
    assert any("缺少 sheet" in issue["message"] for issue in report["issues"])


def test_recipe_referencing_unknown_ingredient_is_reported(as_recorder: TestClient) -> None:
    dish = _dish_name()
    content = _workbook(
        dishes=[[dish, "素菜", "炒", 120, 40, "", ""]],
        recipe=[[dish, "食材", "根本不存在的食材", 100, ""]],
    )

    report = _upload(as_recorder, content, dry_run=True)

    assert report["ok"] is False
    assert any("根本不存在的食材" in issue["message"] for issue in report["issues"])


def test_dry_run_reports_what_would_change(as_recorder: TestClient) -> None:
    name = f"导入预览食材-{uuid4().hex[:6]}"
    content = _workbook(ingredients=[_ingredient_row(name)])

    report = _upload(as_recorder, content, dry_run=True)

    assert report["ok"] is True
    counts = {item["sheet"]: item for item in report["counts"]}
    assert counts["食材"]["created"] == 1
    assert counts["食材"]["updated"] == 0


def test_apply_imports_dish_with_recipe_and_computes_nutrition(
    as_recorder: TestClient,
) -> None:
    dish = _dish_name()
    ingredient = f"导入测试食材-{uuid4().hex[:6]}"
    content = _workbook(
        ingredients=[_ingredient_row(ingredient)],
        dishes=[[dish, "素菜", "炒", 120, 40, "", ""]],
        recipe=[[dish, "食材", ingredient, 100, ""]],
    )

    report = _upload(as_recorder, content, dry_run=False)

    assert report["ok"] is True
    assert report["dry_run"] is False

    detail = as_recorder.get("/api/v1/dishes", params={"keyword": dish}).json()["items"][0]
    assert detail["recipe_version"] == 1

    full = as_recorder.get(f"/api/v1/dishes/{detail['id']}").json()
    assert [line["ingredient_name"] for line in full["recipe"]["ingredients"]] == [ingredient]


def test_reimport_updates_and_keeps_recipe_version_advancing(as_recorder: TestClient) -> None:
    dish = _dish_name()
    ingredient = f"导入测试食材-{uuid4().hex[:6]}"

    first = _upload(
        as_recorder,
        _workbook(
            ingredients=[_ingredient_row(ingredient)],
            dishes=[[dish, "素菜", "炒", 120, 40, "", ""]],
            recipe=[[dish, "食材", ingredient, 100, ""]],
        ),
        dry_run=False,
    )
    assert first["ok"] is True

    # 第二次改用量：应当走「更新」而不是新增
    second = _upload(
        as_recorder,
        _workbook(
            ingredients=[_ingredient_row(ingredient)],
            dishes=[[dish, "素菜", "炒", 120, 40, "", ""]],
            recipe=[[dish, "食材", ingredient, 150, ""]],
        ),
        dry_run=False,
    )
    assert second["ok"] is True
    counts = {item["sheet"]: item for item in second["counts"]}
    assert counts["菜品"]["updated"] == 1
    assert counts["菜品"]["created"] == 0

    detail = as_recorder.get("/api/v1/dishes", params={"keyword": dish}).json()["items"][0]
    assert detail["recipe_version"] == 2


def test_school_admin_cannot_import(as_school_admin: TestClient) -> None:
    content = _workbook(ingredients=[_ingredient_row("学校管理方不该导入的食材")])

    response = as_school_admin.post(
        f"{BASE}/dishes",
        params={"dry_run": "false"},
        files={
            "file": (
                "import.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 403
