"""Agent 可调用的长期记忆工具"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool
from langgraph.store.base import BaseStore

from agent.common.memory.memory_extractor import retrieve_user_memories

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在同步工具里安全执行异步协程。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()

    return asyncio.run(coro)


@tool
def search_memory(
    query: str,
    limit: int = 5,
    *,
    config: Annotated[RunnableConfig, InjectedToolArg],
    store: Annotated[BaseStore, InjectedToolArg],
) -> str:
    """搜索当前用户的长期记忆与当前会话背景。"""
    user_id = config.get("configurable", {}).get("user_id", "default")
    session_id = config.get("configurable", {}).get("thread_id")
    retrieved = _run_async(
        retrieve_user_memories(
            store=store,
            user_id=str(user_id),
            query=query,
            session_id=str(session_id) if session_id else None,
        )
    )

    lines = []
    for title, items in (
        ("长期偏好/事实", retrieved.get("profile", [])),
        ("当前会话背景", retrieved.get("episodic", [])),
    ):
        if not items:
            continue
        lines.append(f"{title}:")
        for item in items[:limit]:
            lines.append(f"- [{item['category']}] {item['content']}")

    if not lines:
        return "未找到相关记忆。"
    return "\n".join(lines)


def get_memory_tools() -> list:
    """返回记忆工具列表"""
    return [search_memory]
