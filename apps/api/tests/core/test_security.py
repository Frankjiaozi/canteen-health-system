"""口令哈希的行为约定。"""

from __future__ import annotations

from app.core.security import hash_password, verify_password


def test_hash_is_not_reversible_and_verifies() -> None:
    password_hash = hash_password("canteen@2026")

    assert "canteen@2026" not in password_hash
    assert password_hash.startswith("$2b$")
    assert verify_password("canteen@2026", password_hash) is True


def test_same_password_produces_different_hashes() -> None:
    """自带随机盐：同一口令两次哈希必须不同，否则说明盐没生效。"""
    first = hash_password("canteen@2026")
    second = hash_password("canteen@2026")

    assert first != second
    assert verify_password("canteen@2026", first) is True
    assert verify_password("canteen@2026", second) is True


def test_wrong_password_is_rejected() -> None:
    assert verify_password("wrong-password", hash_password("canteen@2026")) is False


def test_malformed_hash_returns_false_instead_of_raising() -> None:
    """数据库里出现脏数据时应当拒绝登录，而不是把 500 抛到用户面前。"""
    assert verify_password("canteen@2026", "not-a-bcrypt-hash") is False
    assert verify_password("canteen@2026", "") is False
