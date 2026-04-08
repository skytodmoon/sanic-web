"""PostgreSQL Checkpointer 工厂 — 基于 langgraph-checkpoint-postgres"""

import logging
import os

from psycopg import AsyncConnection

logger = logging.getLogger(__name__)

_checkpointer = None
_conn = None


def _build_psycopg3_conninfo() -> str:
    """从 SQLALCHEMY_DATABASE_URI 环境变量构建 psycopg3 连接串。

    SQLAlchemy 格式: postgresql+psycopg2://user:pass@host:port/db
    psycopg3 格式:   postgresql://user:pass@host:port/db
    """
    uri = os.getenv(
        "SQLALCHEMY_DATABASE_URI",
        "postgresql+psycopg2://aix_db:1@127.0.0.1:5432/aix_db",
    )
    # 去掉 SQLAlchemy 驱动后缀
    return uri.replace("postgresql+psycopg2://", "postgresql://")


async def get_postgres_checkpointer():
    """获取单例 AsyncPostgresSaver，首次调用时创建连接和表。"""
    global _checkpointer, _conn

    if _checkpointer is not None:
        return _checkpointer

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    conn_string = _build_psycopg3_conninfo()
    logger.info("初始化 PostgreSQL Checkpointer...")

    _conn = await AsyncConnection.connect(
        conn_string, autocommit=True, prepare_threshold=0
    )
    _checkpointer = AsyncPostgresSaver(conn=_conn)
    await _checkpointer.setup()

    logger.info("PostgreSQL Checkpointer 初始化完成")
    return _checkpointer
