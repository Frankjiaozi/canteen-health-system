"""每日采集的业务逻辑。

这一域的设计目标只有一个：**每天录入的成本必须极低**。所以采集单一次呈现当天该填的
全部内容（勾选供应的菜、每人次、油盐糖总量、剩餐、异常），提交时一并落库，
并顺手把当餐的营养结果重算一遍——需求里的闭环「录入 → 大屏看到当日营养」
就是在这一步接上的。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessRuleError
from app.core.logging import get_logger
from app.modules.collection import repository
from app.modules.collection.schemas import (
    AnomalyRead,
    DailyLogPage,
    DailyLogSaved,
    DailyLogSheet,
    DailyLogSummary,
    DailyLogWrite,
    LoggedDish,
)
from app.modules.menu import service as menu_service
from app.modules.nutrition import service as nutrition_service
from app.shared.enums import MANUAL_ANOMALY_FLAGS, AnomalyFlag, MealType
from app.shared.nutrition_values import VALUE_TYPE_DESCRIPTIONS, pick_best

logger = get_logger(__name__)


@dataclass
class _NutritionPeek:
    energy_kcal: str
    source: str


def build_sheet(session: Session, *, on_date: date, meal_type: MealType) -> DailyLogSheet:
    """组装采集单：当天该填什么、已经填了什么，一次给全。

    **整份菜品库都列出来**，菜单上有的先勾好。早先只在没有菜单时才列整库，
    结果是「菜单一旦排好，临时加一道菜就没地方勾」——而临时换菜在后厨是常态。
    勾选是权威：提交时按勾选的清单整份覆盖菜单日。
    """
    served = {
        item.dish_id: item
        for item in repository.load_menu_items(session, on_date=on_date, meal_type=meal_type)
    }
    candidates = repository.load_active_dishes(session)
    # 排好菜单的排前面：录入员先看到的就是「今天计划做的那几道」，
    # 要临时加菜再往下列；整库混在一起按类别排，找计划里的菜得来回找
    candidates.sort(key=lambda dish: (dish.id not in served, dish.category, dish.name))
    log = repository.get_log(session, on_date=on_date, meal_type=meal_type)
    items = {item.dish_id: item for item in repository.load_items(session, log.id)} if log else {}
    peek = _nutrition_peek(session, on_date=on_date, meal_type=meal_type)

    rows: list[LoggedDish] = []
    for dish in candidates:
        menu_item = served.get(dish.id)
        item = items.get(dish.id)
        nutrition = peek.get(dish.id)
        rows.append(
            LoggedDish(
                dish_id=str(dish.id),
                name=dish.name,
                category_label=dish.category.label,
                cooking_method_label=dish.cooking_method.label,
                # 采集提交之前，菜单日上写的是「计划供应」，采集提交之后写的是「实际供应」。
                # 所以「计划」这个标记只在提交之前成立——提交完还给每道菜挂「计划」，
                # 等于把实际做的事说成计划做的事。计划份数不受影响，它一直留着供对账。
                is_planned=menu_item is not None and log is None,
                selected=menu_item is not None,
                planned_servings=(
                    None if menu_item is None else _opt_str(menu_item.planned_servings)
                ),
                servings_produced=None if item is None else str(item.servings_produced),
                leftover_ratio=None if item is None else _opt_str(item.leftover_ratio),
                leftover_weight_g=None if item is None else _opt_str(item.leftover_weight_g),
                is_substituted=False if menu_item is None else menu_item.is_substituted,
                substitution_note=None if menu_item is None else menu_item.substitution_note,
                nutrition_source=None if nutrition is None else nutrition.source,
                energy_kcal=None if nutrition is None else nutrition.energy_kcal,
            )
        )

    if not served:
        warning = "这一天还没有确认菜单。从下面勾出今天实际供应的菜品，勾选即写入当天菜单日。"
    elif log is None:
        warning = (
            "这份菜单是「明日菜单与采购」排好的计划：标了「计划」的菜已经勾上，"
            "按实际供应核对——临时加了菜就顺手勾上，没做的取消勾选，保存即按实际覆盖。"
        )
    else:
        warning = None

    return DailyLogSheet(
        date=on_date,
        meal_type=meal_type,
        meal_type_label=meal_type.label,
        saved=log is not None,
        submitted_at=None if log is None else log.submitted_at,
        diner_count=None if log is None else log.diner_count,
        oil_total_g=None if log is None else str(log.oil_total_g),
        salt_total_g=None if log is None else str(log.salt_total_g),
        sugar_total_g=None if log is None else str(log.sugar_total_g),
        leftover_weight_g=None if log is None else _opt_str(log.leftover_weight_g),
        note=None if log is None else log.note,
        anomaly_flags=_flag_rows(None if log is None else log.anomaly_flags),
        dishes=rows,
        menu_confirmed=bool(served),
        warning=warning,
    )


def has_collection(session: Session, *, on_date: date, meal_type: MealType) -> bool:
    """这一天这一餐是否已经录过采集。

    别的域要判断「能不能往这天写菜单」，得走这里问，而不是自己去读 collection 的表。
    """
    return repository.get_log(session, on_date=on_date, meal_type=meal_type) is not None


def save_sheet(
    session: Session,
    *,
    on_date: date,
    payload: DailyLogWrite,
    actor_id: UUID | None,
) -> DailyLogSaved:
    """保存采集单：确认菜单、写明细、写总量，并重算当餐营养结果。

    顺序不能颠倒：菜单要先落库，营养计算才知道这一餐有哪些菜；明细要先写，
    人均摄入才算得出「吃掉多少」。
    """
    if not payload.dishes:
        raise BusinessRuleError("至少要勾选一道当天供应的菜品，否则这一餐没有可核算的内容")

    seen: set[UUID] = set()
    for row in payload.dishes:
        if row.dish_id in seen:
            raise BusinessRuleError("同一道菜只能出现一次，请检查勾选的菜品")
        seen.add(row.dish_id)

    menu_service.confirm_menu_day(
        session,
        on_date=on_date,
        meal_type=payload.meal_type,
        dishes=[
            menu_service.ConfirmedDish(
                dish_id=row.dish_id,
                is_substituted=row.is_substituted,
                note=row.substitution_note,
            )
            for row in payload.dishes
        ],
        created_by=actor_id,
    )

    # 系统回写的标记要原样留住：它是校准算出来的结论，不该因为重新保存一次就消失
    existing = repository.get_log(session, on_date=on_date, meal_type=payload.meal_type)
    manual_values = {member.value for member in MANUAL_ANOMALY_FLAGS}
    system_flags = [
        flag for flag in (existing.anomaly_flags if existing else []) if flag not in manual_values
    ]
    submitted_at = datetime.now(get_settings().timezone)
    log = repository.upsert_log(
        session,
        on_date=on_date,
        meal_type=payload.meal_type,
        diner_count=payload.diner_count,
        oil_total_g=payload.oil_total_g,
        salt_total_g=payload.salt_total_g,
        sugar_total_g=payload.sugar_total_g,
        leftover_weight_g=payload.leftover_weight_g,
        note=payload.note,
        anomaly_flags=[*(member.value for member in payload.anomaly_flags), *system_flags],
        submitted_by=actor_id,
        submitted_at=submitted_at,
    )

    repository.replace_items(
        session,
        daily_log_id=log.id,
        items=[
            {
                "dish_id": row.dish_id,
                "servings_produced": row.servings_produced,
                "leftover_ratio": row.leftover_ratio,
                "leftover_weight_g": row.leftover_weight_g,
                "note": row.note,
            }
            for row in payload.dishes
        ],
    )

    report = nutrition_service.compute_menu_day(
        session, on_date=on_date, meal_type=payload.meal_type
    )
    session.commit()
    logger.info(
        "采集已保存：%s %s，%d 道菜，营养结果 %d 条",
        on_date,
        payload.meal_type.label,
        len(payload.dishes),
        report.rows,
    )
    return DailyLogSaved(
        date=on_date,
        meal_type=payload.meal_type,
        meal_type_label=payload.meal_type.label,
        dish_count=len(payload.dishes),
        nutrition_rows=report.rows,
        submitted_at=submitted_at,
        calibration_note=("当天已跑过校准，可到「抽样纠偏」页看理论值、校准值与实测值的对照"),
    )


def list_logs(
    session: Session, *, page: int, page_size: int, start: date | None, end: date | None
) -> DailyLogPage:
    rows, total = repository.list_logs(
        session, page=page, page_size=page_size, start=start, end=end
    )
    return DailyLogPage(
        items=[
            DailyLogSummary(
                date=log.date,
                meal_type=log.meal_type,
                meal_type_label=log.meal_type.label,
                diner_count=log.diner_count,
                oil_total_g=str(log.oil_total_g),
                salt_total_g=str(log.salt_total_g),
                sugar_total_g=str(log.sugar_total_g),
                leftover_weight_g=_opt_str(log.leftover_weight_g),
                dish_count=dish_count,
                waste_ratio=_waste_ratio(log.leftover_weight_g, produced_g),
                anomaly_flags=_flag_rows(log.anomaly_flags),
                submitted_at=log.submitted_at,
                submitted_by_name=submitter,
            )
            for log, dish_count, produced_g, submitter in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def apply_calibration_residual_flag(
    session: Session, *, on_date: date, meal_type: MealType, flagged: bool
) -> bool:
    """把「当时总量与校准预测对不上」这一结论回写到当天记录上。

    这是跨域调用（校准 → 采集）。写成标记而不是直接拒收，是因为这一天的数据
    仍然要用（它只是不适合进预测的历史序列），而且录入员很可能当天就发现并改对了——
    那时再跑一次校准，标记会自动撤掉。
    """
    log = repository.get_log(session, on_date=on_date, meal_type=meal_type)
    if log is None:
        return False
    return repository.set_anomaly_flag(
        session, log=log, flag=AnomalyFlag.CALIBRATION_RESIDUAL.value, enabled=flagged
    )


def _flag_rows(flags: list[str] | None) -> list[AnomalyRead]:
    known = {member.value for member in AnomalyFlag}
    manual = {member.value for member in MANUAL_ANOMALY_FLAGS}
    return [
        AnomalyRead(
            value=value,
            label=AnomalyFlag(value).label if value in known else value,
            system=value not in manual,
        )
        for value in (flags or [])
    ]


def _nutrition_peek(
    session: Session, *, on_date: date, meal_type: MealType
) -> dict[UUID, _NutritionPeek]:
    """当餐每道菜展示用的单份能量，取证据最强的一份。

    录入时能看见折算出来的能量，录入员才有机会一眼发现「这道菜今天不对」。
    """
    rows = nutrition_service.load_per_serving_rows(session, on_date=on_date, meal_type=meal_type)
    best = pick_best(
        rows, dish_of=lambda row: row.dish_id, value_type_of=lambda row: row.value_type
    )
    return {
        dish_id: _NutritionPeek(
            energy_kcal=str(row.energy_kcal),
            source=VALUE_TYPE_DESCRIPTIONS[row.value_type],
        )
        for dish_id, row in best.items()
    }


def _waste_ratio(leftover_weight_g: Decimal | None, produced_g: Decimal | None) -> str | None:
    if leftover_weight_g is None or not produced_g:
        return None
    return str((leftover_weight_g / produced_g).quantize(Decimal("0.0001")))


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)
