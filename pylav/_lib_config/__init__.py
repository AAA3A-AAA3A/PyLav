from __future__ import annotations

import asyncio
from logging import getLogger
from typing import TYPE_CHECKING

import aiopath
import ujson
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from pylav._config import CONFIG_DIR
from pylav._lib_config.models import Base, LibConfigEntry

if TYPE_CHECKING:
    from pylav.client import Client

LOGGER = getLogger("red.PyLink.LibConfigManager")


class LibConfigManager:
    def __init__(self, client: Client):
        __database_folder: aiopath.AsyncPath = CONFIG_DIR
        __default_db_name: aiopath.AsyncPath = __database_folder / "config.db"
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{__default_db_name}", json_deserializer=ujson.loads, json_serializer=ujson.dumps
        )
        from sqlalchemy.dialects.sqlite import Insert

        self._insert = Insert
        self._session = sessionmaker(self._engine, expire_on_commit=False, class_=AsyncSession)
        self._client = client
        self._config_folder = CONFIG_DIR
        event.listen(self._engine.sync_engine, "connect", self.on_db_connect)

    @staticmethod
    def on_db_connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA temp_store=2")
        cursor.execute("PRAGMA read_uncommitted=1")
        cursor.execute("PRAGMA optimize")
        cursor.close()

    async def initialize(self):
        await self.create_tables()

    @property
    def client(self) -> Client:
        return self._client

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session(self) -> AsyncSession:
        return self._session()

    async def close(self):
        await self._engine.dispose()

    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.commit()

    async def get_config(self) -> dict | None:
        async with self.session as session:
            result = await session.execute(select(LibConfigEntry))
            result = result.scalars().first()
            if result:
                return result.as_dict()

    async def upsert_config(self, config: dict) -> dict:
        async with self.session as session:
            async with session.begin():
                insert_op = await asyncio.to_thread(self._insert(LibConfigEntry).values, [config])
                new_values = config.copy()
                del new_values["id"]
                upset_op = insert_op.on_conflict_do_update(index_elements=["id"], set_=new_values)
                await session.execute(upset_op)
        return config
