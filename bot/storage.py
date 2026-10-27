import json
from typing import Any, Dict, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from . import db


def _key(key: StorageKey) -> str:
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.thread_id}:{key.destiny}"


class PgStorage(BaseStorage):
    """FSM-хранилище в Postgres: функции Vercel не помнят память между запросами."""

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        await db.fsm_set_state(_key(key), value)

    async def get_state(self, key: StorageKey) -> Optional[str]:
        row = await db.fsm_get(_key(key))
        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        await db.fsm_set_data(_key(key), json.dumps(data, ensure_ascii=False))

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        row = await db.fsm_get(_key(key))
        return json.loads(row["data"]) if row else {}

    async def close(self) -> None:
        return None
