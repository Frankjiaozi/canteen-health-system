"""密码与令牌安全。

密码哈希用 pwdlib（bcrypt 后端）。刻意不用 passlib：该项目已停止维护，
且与 bcrypt 5.x 不兼容（读取 `bcrypt.__about__` 会直接抛错）。

令牌相关的函数在「认证与 RBAC」模块加入本文件。
"""

from __future__ import annotations

from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

# 显式指定 bcrypt：不用 PasswordHash.recommended()，避免运行环境里装了 argon2 时
# 哈希算法无声漂移，导致不同机器的口令库不通用
_password_hasher = PasswordHash((BcryptHasher(),))


def hash_password(plain_password: str) -> str:
    """生成口令哈希。同一口令每次结果不同（自带随机盐）。"""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验口令。哈希格式非法时返回 False，不抛异常。"""
    try:
        return _password_hasher.verify(plain_password, password_hash)
    except Exception:
        return False
