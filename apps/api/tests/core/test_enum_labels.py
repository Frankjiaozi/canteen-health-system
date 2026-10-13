"""枚举中文文案的完整性。

这里盯的是一类真实发生过的缺陷：`StrEnum` 之间按值相等，若把文案表按「取值」索引，
不同枚举里同名的取值会互相覆盖——`UserRole.RECORDER` 会取到
`FeedbackSource.RECORDER` 的文案，`DishCategory.VEGETABLE`（素菜）会取到
`IngredientCategory.VEGETABLE`（蔬菜类）的文案。
"""

from __future__ import annotations

from app.shared import enums
from app.shared.enums import (
    ENUM_LABELS,
    DishCategory,
    FeedbackSource,
    IngredientCategory,
    LabelledStrEnum,
    UserRole,
)


def _all_labelled_enum_classes() -> list[type[LabelledStrEnum]]:
    return [
        obj
        for obj in vars(enums).values()
        if isinstance(obj, type) and issubclass(obj, LabelledStrEnum) and obj is not LabelledStrEnum
    ]


def test_every_enum_member_has_an_explicit_chinese_label() -> None:
    classes = _all_labelled_enum_classes()
    assert classes, "未发现任何带文案的枚举"

    for enum_cls in classes:
        for member in enum_cls:
            key = (enum_cls, member.value)
            assert key in ENUM_LABELS, f"{enum_cls.__name__}.{member.name} 缺少中文文案"
            assert ENUM_LABELS[key] != member.value, (
                f"{enum_cls.__name__}.{member.name} 的文案退回了英文取值"
            )


def test_labels_do_not_leak_between_enum_classes() -> None:
    """跨枚举同名取值必须各自取到自己的文案。"""
    assert UserRole.RECORDER.label == "食堂录入员"
    assert FeedbackSource.RECORDER.label == "录入员代录"

    assert DishCategory.VEGETABLE.label == "素菜"
    assert IngredientCategory.VEGETABLE.label == "蔬菜类"
