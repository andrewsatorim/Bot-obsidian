from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

from app.ports.storage_port import StoragePort

logger = logging.getLogger(__name__)


class SqliteStorage(StoragePort):
    """SQLite-based key-value storage for bot state persistence."""

    def __init__(self, db_path: str = "data/bot_state.db") -> None:
        self._db_path = db_path
        self._initialized = False

    async def _ensure_table(self) -> None:
        if self._initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS kv_store "
                "(key TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            await db.commit()
        self._initialized = True

    async def save(self, key: str, data: Any) -> None:
        await self._ensure_table()
        now = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(data) if not isinstance(data, str) else data
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO kv_store (key, data, updated_at) VALUES (?, ?, ?)",
                (key, serialized, now),
            )
            await db.commit()
        logger.debug("saved key=%s", key)

    async def load(self, key: str) -> Optional[Any]:
        await self._ensure_table()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT data FROM kv_store WHERE key = ?", (key,))
            row = await cursor.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return row[0]
