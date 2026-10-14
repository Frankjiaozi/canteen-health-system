"""消耗量预测的算法（纯函数，不碰数据库）。

公式只有一行：**预测份数 = 同星期移动平均 × 日历修正系数**。

为什么不用大模型：数据量小（8 周）、序列短、需要可解释、需要稳定复现——这四条都指向
统计模型。用大模型去拟合几十天的销量序列，准确率和可解释性都会更差。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import fmean, pstdev

from app.shared.enums import HolidayKind

MODEL_VERSION = "weekday-ma-v1"

#: 同星期移动平均取最近几个「同一个星期几」。8 周历史下每个星期几有 8 个样本；
#: 取 6 周是留出余量：太短会被一次偶发波动带偏，太长会让早就变了的菜品热度不肯退场。
DEFAULT_WINDOW = 6

#: 历史样本少于这个数就不给预测。两周的同星期样本只有 2 个，均值没有意义。
MIN_SAMPLES = 3

#: 置信区间至少有这么宽。样本完全一致时标准差是 0，报出「误差 0」等于宣称预测绝对准确。
MIN_INTERVAL_RATIO = Decimal("0.10")

#: 放假日的份数折减。假期留校人数通常只剩一小部分，但食堂仍要开餐，所以不是 0。
HOLIDAY_FACTOR = Decimal("0.45")

#: 调休上班的周末：人在校，但周末的用餐习惯仍与工作日不同，取一个略高于 1 的系数。
WORKDAY_FACTOR = Decimal("1.05")

#: 置信区间取几倍标准差。约 95% 对应的 1.96 在样本只有 6 个时偏乐观，取 1.5 更诚实。
INTERVAL_SIGMA = Decimal("1.5")


@dataclass(frozen=True, slots=True)
class HistoryPoint:
    """一次历史供应记录。"""

    date: date
    servings: Decimal


@dataclass(frozen=True, slots=True)
class ForecastResult:
    predicted: Decimal
    lower: Decimal
    upper: Decimal
    #: 参与计算的样本（日期 + 份数），写进 features 快照供复盘
    samples: tuple[HistoryPoint, ...]
    #: 移动平均值，即日历修正之前的值
    baseline: Decimal
    adjustment: Decimal
    calendar_note: str | None
    #: SAME_WEEKDAY = 同星期几平均；OVERALL = 同星期样本不足，退化为全期平均
    basis: str


def day_adjustment(target: date, holidays: dict[date, HolidayKind]) -> tuple[Decimal, str | None]:
    """日历修正系数。

    放假当天下调、调休上班的周末按工作日处理，其余日子不做修正。
    系数取的是经验值而不是拟合出来的——第一版不做需求里明确划到范围外的
    考试周、军训、运动会，也不做天气与季节，这两处都没有稳定数据源。
    """
    kind = holidays.get(target)
    if kind is HolidayKind.HOLIDAY:
        return HOLIDAY_FACTOR, f"{target.isoformat()} 为法定假日，在校人数下降"
    if kind is HolidayKind.WORKDAY:
        return WORKDAY_FACTOR, f"{target.isoformat()} 为调休上班日，按工作日处理"
    return Decimal("1"), None


def same_weekday_baseline(
    history: Sequence[HistoryPoint], *, target: date, window: int = DEFAULT_WINDOW
) -> tuple[Decimal, tuple[HistoryPoint, ...]]:
    """取最近若干个「同一个星期几」的份数做平均。

    只认同星期几：食堂的份数在周一与周五之间能差出一大截，把整周混在一起平均，
    得到的数字哪天都不像。只作展示与单测用，正式的预测走 `forecast_dish`。
    """
    matched = [
        point
        for point in history
        if point.date < target and point.date.weekday() == target.weekday()
    ]
    matched.sort(key=lambda point: point.date)
    selected = tuple(matched[-window:])
    if not selected:
        return Decimal("0"), ()
    return Decimal(str(fmean([float(point.servings) for point in selected]))), selected


def weekday_profile(histories: Sequence[Sequence[HistoryPoint]]) -> dict[int, Decimal]:
    """星期几的整体规律：某天平均份数 ÷ 全期平均份数。

    它由**所有菜的历史一起**估出来，而不是靠单道菜。原因很实在：轮换菜单里一道菜
    每四五天才出现一次，靠它自己根本估不出「周六比周三少一半」这种规律，
    但这件事对所有菜同时成立，合起来看就非常清楚。

    用途只有一个：某道菜同星期样本不足时，用它把全期平均缩放到当天该有的量级。
    少了这一步，退化的预测会在周末高估一倍以上。
    """
    by_weekday: dict[int, list[float]] = {index: [] for index in range(7)}
    everything: list[float] = []
    for history in histories:
        for point in history:
            value = float(point.servings)
            by_weekday[point.date.weekday()].append(value)
            everything.append(value)
    if not everything:
        return {}
    overall = fmean(everything)
    if overall <= 0:
        return {}
    return {
        weekday: Decimal(str(fmean(values) / overall))
        for weekday, values in by_weekday.items()
        if values
    }


def forecast_dish(
    history: Sequence[HistoryPoint],
    *,
    target: date,
    adjustment: Decimal = Decimal("1"),
    calendar_note: str | None = None,
    window: int = DEFAULT_WINDOW,
    profile: dict[int, Decimal] | None = None,
) -> ForecastResult | None:
    """预测一道菜在某天的份数。样本不足时返回 None——不给数字，好过给一个凑出来的数字。

    同星期样本不够时**退化为「全期平均 × 星期几规律」**，而不是直接放弃：轮换菜单里的菜往往
    每隔四五天才出现一次，严格只认同星期几的话，一多半的菜都会因为「同一个星期几
    只出现过一两次」而没有预测。退化这件事会随结果一起报出去，不隐瞒。
    """
    earlier = [point for point in history if point.date < target]
    exact = [point for point in earlier if point.date.weekday() == target.weekday()]
    exact.sort(key=lambda point: point.date)
    samples = tuple(exact[-window:])
    basis = "SAME_WEEKDAY"
    if len(samples) < MIN_SAMPLES:
        earlier_subject = sorted(earlier, key=lambda point: point.date)[-(window * 2) :]
        if len(earlier_subject) < MIN_SAMPLES:
            return None
        samples = tuple(earlier_subject)
        basis = "WEEKDAY_PROFILE"
        fallback = (profile or {}).get(target.weekday(), Decimal("1"))
        baseline = Decimal(str(fmean([float(point.servings) for point in samples]))) * fallback

    if basis == "SAME_WEEKDAY":
        baseline = Decimal(str(fmean([float(point.servings) for point in samples])))

    predicted = (baseline * adjustment).quantize(Decimal("0.01"))
    # 区间来自历史本身的离散程度，外加一个下限：样本一模一样时也不该说「误差为零」
    values = [float(point.servings) for point in samples]
    spread = Decimal(str(pstdev(values))) if len(values) > 1 else Decimal("0")
    half_width = max(
        (spread * adjustment * INTERVAL_SIGMA).quantize(Decimal("0.01")),
        (predicted * MIN_INTERVAL_RATIO).quantize(Decimal("0.01")),
    )
    return ForecastResult(
        predicted=predicted,
        lower=max(Decimal("0"), (predicted - half_width).quantize(Decimal("0.01"))),
        upper=(predicted + half_width).quantize(Decimal("0.01")),
        samples=samples,
        baseline=baseline.quantize(Decimal("0.01")),
        adjustment=adjustment,
        calendar_note=calendar_note,
        basis=basis,
    )


def mean_absolute_percentage_error(
    pairs: Sequence[tuple[Decimal, Decimal]],
) -> Decimal | None:
    """回测用的 MAPE。返回 None 表示没有可算的样本，而不是 0——0 会被读成「完全准确」。"""
    usable = [(actual, predicted) for actual, predicted in pairs if actual > 0]
    if not usable:
        return None
    total = sum((abs(predicted - actual) / actual for actual, predicted in usable), Decimal("0"))
    return (total / Decimal(len(usable))).quantize(Decimal("0.0001"))


def is_anomalous(flags: Sequence[str], *, excluded: Sequence[str]) -> bool:
    """这一天要不要排除在历史序列之外。

    临时接待、菜品停供、设备故障都会让那天的份数偏离常态，
    进了移动平均就会把预测带偏——这是需求里点名的一条。
    """
    return any(flag in excluded for flag in flags)


def ingredient_requirements(
    per_serving: dict[str, Decimal], predicted_servings: Decimal
) -> dict[str, Decimal]:
    """由预测份数反推食材需求量：单份用量 × 预测份数。"""
    return {
        name: (quantity * predicted_servings).quantize(Decimal("0.001"))
        for name, quantity in per_serving.items()
    }


def weekday_label(value: date) -> str:
    names = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
    return names[value.weekday()]


def history_window(target: date, *, weeks: int) -> tuple[date, date]:
    """回测或取历史用的日期区间。"""
    return target - timedelta(days=weeks * 7), target
