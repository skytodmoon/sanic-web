import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent.common.enhanced_common_agent import EnhancedCommonAgent
from agent.common.memory.memory_extractor import (
    extract_and_save_memories,
    retrieve_user_memories,
)
from agent.common.memory.memory_tools import get_memory_tools
from agent.common.memory import pg_store as pg_store_module
from agent.common.memory.pg_store import PostgresMemoryStore


class FakeStore:
    def __init__(self, search_results=None):
        self.put_calls = []
        self.search_calls = []
        self.search_results = search_results or {}

    async def aput(self, namespace, key, value, index=None, ttl=None):
        self.put_calls.append(
            {
                "namespace": namespace,
                "key": key,
                "value": value,
                "ttl": ttl,
                "index": index,
            }
        )

    async def asearch(self, namespace_prefix, *, query=None, filter=None, limit=10, offset=0, refresh_ttl=None):
        self.search_calls.append(
            {
                "namespace_prefix": namespace_prefix,
                "query": query,
                "filter": filter,
                "limit": limit,
                "offset": offset,
            }
        )
        key = tuple(namespace_prefix)
        return list(self.search_results.get(key, []))


def test_get_memory_tools_only_exposes_search():
    tools = get_memory_tools()

    assert len(tools) == 1
    assert tools[0].name == "search_memory"


def test_extract_and_save_memories_uses_question_only_and_writes_profile_and_chat_context(monkeypatch):
    class FakeLLM:
        async def ainvoke(self, prompt):
            assert "助手回答" not in prompt
            assert "以后都用中文回答" in prompt
            return SimpleNamespace(
                content="""[
                    {"category":"instruction","content":"以后都用中文回答","slot":"language","confidence":0.98},
                    {"category":"context","content":"当前会话围绕长期记忆改造展开","confidence":0.83}
                ]"""
            )

    monkeypatch.setattr(
        "agent.common.memory.memory_extractor.get_llm",
        lambda temperature=0: FakeLLM(),
    )

    store = FakeStore()

    saved = asyncio.run(
        extract_and_save_memories(
            store=store,
            record_id=42,
            user_id="1",
            session_id="chat-7",
            question="以后都用中文回答。我们正在做长期记忆改造。",
        )
    )

    assert saved == 2
    assert store.put_calls[0]["namespace"] == ("user", "1", "profile", "instruction")
    assert store.put_calls[0]["value"]["slot"] == "language"
    assert store.put_calls[0]["ttl"] is None
    assert store.put_calls[1]["namespace"] == ("user", "1", "episodic", "chat", "chat-7", "context")
    assert store.put_calls[1]["ttl"] == 14 * 24 * 60 * 60


def test_retrieve_user_memories_returns_structured_profile_and_episodic_sections():
    profile_item = SimpleNamespace(
        value={
            "content": "以后都用中文回答",
            "category": "instruction",
            "memory_kind": "profile",
            "slot": "language",
        }
    )
    episodic_item = SimpleNamespace(
        value={
            "content": "当前会话围绕长期记忆改造展开",
            "category": "context",
            "memory_kind": "episodic",
            "scope_type": "chat",
            "scope_id": "chat-7",
        },
        score=0.92,
    )
    store = FakeStore(
        search_results={
            ("user", "1", "profile"): [profile_item],
            ("user", "1", "episodic", "chat", "chat-7"): [episodic_item],
        }
    )

    context = asyncio.run(
        retrieve_user_memories(
            store=store,
            user_id="1",
            session_id="chat-7",
            query="记忆改造方案",
        )
    )

    assert context["profile"][0]["content"] == "以后都用中文回答"
    assert context["episodic"][0]["content"] == "当前会话围绕长期记忆改造展开"
    assert store.search_calls[0]["namespace_prefix"] == ("user", "1", "profile")
    assert store.search_calls[1]["namespace_prefix"] == ("user", "1", "episodic", "chat", "chat-7")


def test_build_runtime_system_prompt_uses_memory_sections():
    prompt = EnhancedCommonAgent._build_runtime_system_prompt(
        {
            "profile": [{"category": "instruction", "content": "以后都用中文回答"}],
            "episodic": [{"category": "context", "content": "当前会话围绕长期记忆改造展开"}],
        }
    )

    assert "用户长期偏好/事实" in prompt
    assert "当前会话背景" in prompt
    assert "以后都用中文回答" in prompt
    assert "长期记忆改造" in prompt


def test_postgres_memory_store_search_uses_exact_user_id_and_safe_namespace_boundary(monkeypatch):
    captured = {}

    monkeypatch.setattr(pg_store_module, "ensure_agent_memory_schema", lambda: None)

    async def fake_embedding(_query):
        return [0.1, 0.2]

    def fake_execute(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(pg_store_module, "_generate_embedding_safe", fake_embedding)
    monkeypatch.setattr(pg_store_module, "_execute_sql_dict", fake_execute)

    store = PostgresMemoryStore()
    asyncio.run(store.asearch(("user", "1", "profile"), query="中文", limit=5))

    assert "user_id = %s" in captured["sql"]
    assert "namespace = %s OR namespace LIKE %s" in captured["sql"]
    assert "user.1.profile.%" in captured["params"]
    assert "user.1%" not in captured["params"]
