"""独立 SQLite 对话库。保存快照与过程，不保存 Cookie、密钥或模型推理文本。"""

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from .errors import AgentError
from .schemas import Conversation


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, owner TEXT NOT NULL, updated TEXT NOT NULL, data TEXT NOT NULL, busy_until REAL NOT NULL DEFAULT 0)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS sessions_owner ON sessions(owner, updated)"
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, owner: str) -> Conversation:
        conversation = Conversation(
            id=str(uuid4()), title="新的膳食任务", created_at=now(), updated_at=now()
        )
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sessions(id,owner,updated,data) VALUES(?,?,?,?)",
                (conversation.id, owner, conversation.updated_at, self.serialize(conversation)),
            )
        return conversation

    @staticmethod
    def serialize(conversation: Conversation) -> str:
        body = conversation.model_dump(mode="json")
        body["completed_requests"] = conversation.completed_requests[-100:]
        body["request_fingerprints"] = {
            key: value
            for key, value in conversation.request_fingerprints.items()
            if key in body["completed_requests"]
        }
        return json.dumps(body, ensure_ascii=False)

    def get(self, session_id: str, owner: str) -> Conversation:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT data FROM sessions WHERE id=? AND owner=?", (session_id, owner)
            ).fetchone()
        if row is None:
            raise AgentError("对话不存在或不属于当前账号", 404, "not_found")
        return Conversation.model_validate_json(row["data"])

    def list(self, owner: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT data FROM sessions WHERE owner=? ORDER BY updated DESC LIMIT 40", (owner,)
            ).fetchall()
        return [
            {
                "id": item.id,
                "title": item.title,
                "updated_at": item.updated_at,
                "revision": item.revision,
            }
            for item in (Conversation.model_validate_json(row["data"]) for row in rows)
        ]

    def save(self, conversation: Conversation, owner: str):
        conversation.updated_at = now()
        with self.connect() as connection:
            connection.execute(
                "UPDATE sessions SET updated=?,data=? WHERE id=? AND owner=?",
                (conversation.updated_at, self.serialize(conversation), conversation.id, owner),
            )

    def acquire(self, session_id: str, owner: str):
        self.get(session_id, owner)
        with self.connect() as connection:
            changed = connection.execute(
                "UPDATE sessions SET busy_until=? WHERE id=? AND owner=? AND busy_until<?",
                (time.time() + 240, session_id, owner, time.time()),
            ).rowcount
        if not changed:
            raise AgentError("这段对话正在处理任务，请稍后刷新结果", 409, "session_busy")

    def release(self, session_id: str, owner: str):
        with self.connect() as connection:
            connection.execute(
                "UPDATE sessions SET busy_until=0 WHERE id=? AND owner=?", (session_id, owner)
            )
