"""计划发布与实际采集共用的餐次写锁，尚无菜单行时也生效。"""

import hashlib
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.enums import MealType


def lock_meal(session: Session, on_date: date, meal_type: MealType) -> None:
    key = int(hashlib.sha256(f"menu:{on_date}:{meal_type.value}".encode()).hexdigest()[:15], 16)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
