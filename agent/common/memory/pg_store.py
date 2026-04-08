"""PostgreSQL + pgvector 长期记忆 Store — 实现 LangGraph BaseStore 接口"""

import asyncio
import json
import logging
import threading
from collections.abc import Iterable
from datetime import datetime, timezone, timedelta
from typing import Any

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

logger = logging.getLogger(__name__)
_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()


def _execute_sql_dict(sql: str, params: tuple | None = None):
    from services.user_service import execute_sql_dict

    return execute_sql_dict(sql, params)


def _execute_sql_update(sql: str, params: tuple | None = None):
    from services.user_service import execute_sql_update

    return execute_sql_update(sql, params)


def ensure_agent_memory_schema() -> None:
    """确保长期记忆表具备 V1 所需字段和索引。"""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return

        statements = [
            "ALTER TABLE t_agent_memory ADD COLUMN IF NOT EXISTS user_id VARCHAR(100)",
            "ALTER TABLE t_agent_memory ADD COLUMN IF NOT EXISTS memory_kind VARCHAR(32)",
            "ALTER TABLE t_agent_memory ADD COLUMN IF NOT EXISTS scope_type VARCHAR(32)",
            "ALTER TABLE t_agent_memory ADD COLUMN IF NOT EXISTS scope_id VARCHAR(255)",
            "ALTER TABLE t_agent_memory ADD COLUMN IF NOT EXISTS slot VARCHAR(64)",
            "ALTER TABLE t_agent_memory ADD COLUMN IF NOT EXISTS source_record_id BIGINT",
            "ALTER TABLE t_agent_memory ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION",
            "CREATE INDEX IF NOT EXISTS idx_agent_memory_user_kind_updated ON t_agent_memory(user_id, memory_kind, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_agent_memory_user_scope_updated ON t_agent_memory(user_id, scope_type, scope_id, updated_at DESC)",
            """
            UPDATE t_agent_memory
            SET user_id = NULLIF(split_part(namespace, '.', 2), '')
            WHERE user_id IS NULL
              AND namespace LIKE 'user.%'
            """,
            """
            UPDATE t_agent_memory
            SET memory_kind = COALESCE(NULLIF(value->>'memory_kind', ''), 'profile')
            WHERE memory_kind IS NULL
            """,
            """
            UPDATE t_agent_memory
            SET scope_type = COALESCE(
                NULLIF(value->>'scope_type', ''),
                CASE
                    WHEN COALESCE(value->>'memory_kind', memory_kind, 'profile') = 'episodic' THEN 'chat'
                    ELSE 'user'
                END
            )
            WHERE scope_type IS NULL
            """,
            """
            UPDATE t_agent_memory
            SET scope_id = NULLIF(value->>'scope_id', '')
            WHERE scope_id IS NULL AND value ? 'scope_id'
            """,
            """
            UPDATE t_agent_memory
            SET slot = NULLIF(value->>'slot', '')
            WHERE slot IS NULL AND value ? 'slot'
            """,
            """
            UPDATE t_agent_memory
            SET source_record_id = NULLIF(value->>'source_record_id', '')::BIGINT
            WHERE source_record_id IS NULL
              AND value ? 'source_record_id'
              AND NULLIF(value->>'source_record_id', '') IS NOT NULL
            """,
            """
            UPDATE t_agent_memory
            SET confidence = COALESCE(NULLIF(value->>'confidence', '')::DOUBLE PRECISION, 1.0)
            WHERE confidence IS NULL
            """,
        ]
        try:
            for statement in statements:
                _execute_sql_update(statement)
        except Exception as e:
            logger.warning(f"初始化长期记忆 schema 失败，将在运行期依赖现有表结构: {e}")
            return

        _SCHEMA_READY = True

STRUCTURED_COLUMN_EXPRESSIONS = {
    "user_id": "COALESCE(user_id::text, NULLIF(split_part(namespace, '.', 2), ''))",
    "memory_kind": "COALESCE(memory_kind, value->>'memory_kind')",
    "scope_type": "COALESCE(scope_type, value->>'scope_type')",
    "scope_id": "COALESCE(scope_id, value->>'scope_id')",
    "slot": "COALESCE(slot, value->>'slot')",
    "source_record_id": "COALESCE(CAST(source_record_id AS TEXT), value->>'source_record_id')",
    "confidence": "COALESCE(CAST(confidence AS TEXT), value->>'confidence')",
}


def _ns_to_str(namespace: tuple[str, ...]) -> str:
    """命名空间 tuple → 点分字符串"""
    return ".".join(namespace)


def _str_to_ns(s: str) -> tuple[str, ...]:
    """点分字符串 → 命名空间 tuple"""
    return tuple(s.split("."))


def _parse_dt(val) -> datetime:
    """解析时间字段（可能是 datetime 或字符串）"""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.strptime(val, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    return datetime.now(timezone.utc)


def _make_item(row: dict) -> Item:
    """从数据库行构建 Item"""
    return Item(
        value=row["value"] if isinstance(row["value"], dict) else json.loads(row["value"]),
        key=row["key"],
        namespace=_str_to_ns(row["namespace"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _make_search_item(row: dict, score: float = 0.0) -> SearchItem:
    """从数据库行构建 SearchItem"""
    item = _make_item(row)
    return SearchItem(
        value=item.value,
        key=item.key,
        namespace=item.namespace,
        created_at=item.created_at,
        updated_at=item.updated_at,
        score=score,
    )


async def _generate_embedding_safe(text: str):
    """安全地生成 embedding，失败返回 None"""
    try:
        from services.embedding_service import generate_embedding

        return await generate_embedding(text)
    except Exception as e:
        logger.warning(f"生成 embedding 失败: {e}")
        return None


class PostgresMemoryStore(BaseStore):
    """基于 PostgreSQL + pgvector 的长期记忆 Store"""

    supports_ttl = True

    def __init__(self):
        ensure_agent_memory_schema()

    def batch(
        self,
        ops: Iterable[tuple[str, ...] | GetOp | SearchOp | PutOp | ListNamespacesOp],
    ) -> list[Result]:
        """同步批量操作 — 在事件循环中运行异步版本"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self.abatch(ops))
                return future.result()
        return asyncio.run(self.abatch(ops))

    async def abatch(
        self,
        ops: Iterable[tuple[str, ...] | GetOp | SearchOp | PutOp | ListNamespacesOp],
    ) -> list[Result]:
        """异步批量操作 — 核心实现"""
        results: list[Result] = []

        for op in ops:
            if isinstance(op, GetOp):
                results.append(await self._handle_get(op))
            elif isinstance(op, PutOp):
                await self._handle_put(op)
                results.append(None)
            elif isinstance(op, SearchOp):
                results.append(await self._handle_search(op))
            elif isinstance(op, ListNamespacesOp):
                results.append(await self._handle_list_namespaces(op))
            else:
                results.append(None)

        return results

    @staticmethod
    def _derive_user_id(namespace: tuple[str, ...]) -> str | None:
        """从 namespace 中提取 user_id。"""
        if len(namespace) >= 2 and namespace[0] == "user":
            return str(namespace[1])
        return None

    @staticmethod
    def _build_namespace_where(prefix: str) -> tuple[str, list[Any]]:
        """构造边界安全的 namespace 前缀查询。"""
        return "(namespace = %s OR namespace LIKE %s)", [prefix, prefix + ".%"]

    @staticmethod
    def _build_filter_clause(
        filter_dict: dict[str, Any] | None,
    ) -> tuple[str, list[Any]]:
        """将 SearchOp.filter 转换为 SQL 过滤条件。"""
        if not filter_dict:
            return "", []

        filter_sql = []
        filter_params: list[Any] = []
        for fk, fv in filter_dict.items():
            if fk in STRUCTURED_COLUMN_EXPRESSIONS:
                filter_sql.append(f"{STRUCTURED_COLUMN_EXPRESSIONS[fk]} = %s")
                filter_params.append(str(fv))
            else:
                filter_sql.append(f"value->>'{fk}' = %s")
                filter_params.append(str(fv))

        return " AND " + " AND ".join(filter_sql), filter_params

    @staticmethod
    def _extract_structured_metadata(
        namespace: tuple[str, ...], value: dict[str, Any]
    ) -> dict[str, Any]:
        """从 namespace/value 派生结构化元数据列。"""
        user_id = PostgresMemoryStore._derive_user_id(namespace)
        memory_kind = value.get("memory_kind")
        scope_type = value.get("scope_type")
        scope_id = value.get("scope_id")
        slot = value.get("slot")
        source_record_id = value.get("source_record_id")
        confidence = float(value.get("confidence", 1.0))

        if memory_kind is None and len(namespace) >= 3:
            memory_kind = namespace[2]

        if scope_type is None:
            if memory_kind == "episodic" and len(namespace) >= 6:
                scope_type = namespace[3]
            else:
                scope_type = "user"

        if scope_id is None and memory_kind == "episodic" and len(namespace) >= 6:
            scope_id = namespace[4]

        return {
            "user_id": user_id,
            "memory_kind": memory_kind or "profile",
            "scope_type": scope_type,
            "scope_id": scope_id,
            "slot": slot,
            "source_record_id": source_record_id,
            "confidence": confidence,
        }

    async def _handle_get(self, op: GetOp) -> Item | None:
        """获取单个记忆"""
        ns_str = _ns_to_str(op.namespace)
        sql = """
            SELECT namespace, key, value, created_at, updated_at
            FROM t_agent_memory
            WHERE namespace = %s AND key = %s
            AND (expires_at IS NULL OR expires_at > NOW())
        """
        rows = _execute_sql_dict(sql, (ns_str, op.key))
        if not rows:
            return None
        return _make_item(rows[0])

    async def _handle_put(self, op: PutOp) -> None:
        """写入/更新/删除记忆"""
        ns_str = _ns_to_str(op.namespace)

        if op.value is None:
            sql = "DELETE FROM t_agent_memory WHERE namespace = %s AND key = %s"
            _execute_sql_update(sql, (ns_str, op.key))
            return

        embed_text = op.value.get("content", "") or json.dumps(
            op.value, ensure_ascii=False
        )
        embedding = await _generate_embedding_safe(embed_text)

        expires_at = None
        if op.ttl is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=op.ttl)

        value_json = json.dumps(op.value, ensure_ascii=False)
        metadata = self._extract_structured_metadata(op.namespace, op.value)

        if embedding is not None:
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            sql = """
                INSERT INTO t_agent_memory (
                    namespace, key, value, embedding, user_id, memory_kind,
                    scope_type, scope_id, slot, source_record_id, confidence,
                    expires_at, updated_at
                )
                VALUES (%s, %s, CAST(%s AS jsonb), CAST(%s AS vector), %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (namespace, key)
                DO UPDATE SET value = EXCLUDED.value, embedding = EXCLUDED.embedding,
                              user_id = EXCLUDED.user_id, memory_kind = EXCLUDED.memory_kind,
                              scope_type = EXCLUDED.scope_type, scope_id = EXCLUDED.scope_id,
                              slot = EXCLUDED.slot, source_record_id = EXCLUDED.source_record_id,
                              confidence = EXCLUDED.confidence,
                              expires_at = EXCLUDED.expires_at, updated_at = NOW()
            """
            params = (
                ns_str,
                op.key,
                value_json,
                embedding_str,
                metadata["user_id"],
                metadata["memory_kind"],
                metadata["scope_type"],
                metadata["scope_id"],
                metadata["slot"],
                metadata["source_record_id"],
                metadata["confidence"],
                expires_at,
            )
        else:
            sql = """
                INSERT INTO t_agent_memory (
                    namespace, key, value, user_id, memory_kind,
                    scope_type, scope_id, slot, source_record_id, confidence,
                    expires_at, updated_at
                )
                VALUES (%s, %s, CAST(%s AS jsonb), %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (namespace, key)
                DO UPDATE SET value = EXCLUDED.value,
                              user_id = EXCLUDED.user_id, memory_kind = EXCLUDED.memory_kind,
                              scope_type = EXCLUDED.scope_type, scope_id = EXCLUDED.scope_id,
                              slot = EXCLUDED.slot, source_record_id = EXCLUDED.source_record_id,
                              confidence = EXCLUDED.confidence,
                              expires_at = EXCLUDED.expires_at, updated_at = NOW()
            """
            params = (
                ns_str,
                op.key,
                value_json,
                metadata["user_id"],
                metadata["memory_kind"],
                metadata["scope_type"],
                metadata["scope_id"],
                metadata["slot"],
                metadata["source_record_id"],
                metadata["confidence"],
                expires_at,
            )

        _execute_sql_update(sql, params)

    async def _handle_search(self, op: SearchOp) -> list[SearchItem]:
        """搜索记忆 — 支持语义搜索和边界安全前缀匹配"""
        ns_prefix = _ns_to_str(op.namespace_prefix)

        where_sql, where_params = self._build_namespace_where(ns_prefix)
        filter_clause, filter_params = self._build_filter_clause(op.filter)
        user_id = self._derive_user_id(op.namespace_prefix)
        user_clause = ""
        user_params: list[Any] = []

        if user_id is not None:
            user_clause = f" AND {STRUCTURED_COLUMN_EXPRESSIONS['user_id']} = %s"
            user_params.append(str(user_id))

        if op.query:
            query_embedding = await _generate_embedding_safe(op.query)
            if query_embedding:
                embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
                sql = f"""
                    SELECT namespace, key, value, created_at, updated_at,
                           1 - (embedding <=> CAST(%s AS vector)) AS score
                    FROM t_agent_memory
                    WHERE {where_sql}
                    {user_clause}
                    AND embedding IS NOT NULL
                    AND (expires_at IS NULL OR expires_at > NOW())
                    {filter_clause}
                    ORDER BY embedding <=> CAST(%s AS vector)
                    LIMIT %s OFFSET %s
                """
                params = tuple(
                    [embedding_str]
                    + where_params
                    + user_params
                    + filter_params
                    + [embedding_str, op.limit, op.offset]
                )
                rows = _execute_sql_dict(sql, params)
                return [_make_search_item(r, r.get("score", 0.0)) for r in rows]

        sql = f"""
            SELECT namespace, key, value, created_at, updated_at
            FROM t_agent_memory
            WHERE {where_sql}
            {user_clause}
            AND (expires_at IS NULL OR expires_at > NOW())
            {filter_clause}
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
        """
        params = tuple(where_params + user_params + filter_params + [op.limit, op.offset])
        rows = _execute_sql_dict(sql, params)
        return [_make_search_item(r, 0.0) for r in rows]

    async def _handle_list_namespaces(
        self, op: ListNamespacesOp
    ) -> list[tuple[str, ...]]:
        """列出命名空间"""
        where_clauses = ["(expires_at IS NULL OR expires_at > NOW())"]
        params: list[Any] = []

        if op.match_conditions:
            for cond in op.match_conditions:
                match_type = cond.match_type
                path = cond.path
                if match_type == "prefix":
                    prefix = ".".join(path)
                    where_clauses.append("(namespace = %s OR namespace LIKE %s)")
                    params.extend([prefix, prefix + ".%"])
                elif match_type == "suffix":
                    suffix = ".".join(path)
                    where_clauses.append("(namespace = %s OR namespace LIKE %s)")
                    params.extend([suffix, "%." + suffix])

        where_sql = " AND ".join(where_clauses)
        params.extend([op.limit, op.offset])

        sql = f"""
            SELECT DISTINCT namespace
            FROM t_agent_memory
            WHERE {where_sql}
            ORDER BY namespace
            LIMIT %s OFFSET %s
        """
        rows = _execute_sql_dict(sql, tuple(params))

        result = []
        for row in rows:
            ns = _str_to_ns(row["namespace"])
            if op.max_depth is not None:
                ns = ns[: op.max_depth]
            result.append(ns)

        seen = set()
        unique = []
        for ns in result:
            if ns not in seen:
                seen.add(ns)
                unique.append(ns)

        return unique
