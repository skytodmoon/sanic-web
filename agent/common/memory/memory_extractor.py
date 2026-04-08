"""对话后自动记忆提取 + 对话前结构化记忆检索"""

import hashlib
import json
import logging
import re
from typing import Any, Optional

from langgraph.store.base import BaseStore

from common.llm_util import get_llm

logger = logging.getLogger(__name__)

PROFILE_CATEGORIES = {"preference", "fact", "instruction"}
EPISODIC_CATEGORIES = {"context"}
PROFILE_MEMORY_LIMIT = 8
EPISODIC_MEMORY_LIMIT = 5
EPISODIC_MEMORY_TTL_SECONDS = 14 * 24 * 60 * 60
EPISODIC_MEMORY_SCORE_THRESHOLD = 0.65
DEFAULT_SCOPE_TYPE = "chat"
PROFILE_CATEGORY_ORDER = {
    "instruction": 0,
    "preference": 1,
    "fact": 2,
}

EXTRACT_PROMPT = """你是一个长期记忆提取助手。请只根据用户原话，提取值得保留的信息。

## 用户原话
{question}

## 提取规则
只提取以下类型：
1. preference — 稳定偏好，例如语言、格式、输出风格
2. fact — 关于用户的长期事实，例如角色、团队、负责领域
3. instruction — 长期有效的固定指令，例如“以后都用中文回答”
4. context — 仅对当前会话有帮助的重要上下文，例如“当前正在排查长期记忆方案”

## 严格限制
- 只能依据用户原话，不要引用助手说过的话
- 不要猜测，不要补全，不要记录临时闲聊
- 如果一句话只在当前会话有用，标成 context
- 如果一句话是长期偏好或长期规则，优先标成 preference 或 instruction
- slot 仅在能明确归纳为稳定字段时填写，例如 language、output_style、role、project
- confidence 取 0 到 1 之间的小数

## 输出格式
直接输出 JSON 数组，不要输出其他内容。

```json
[
  {{"category": "instruction", "content": "以后都用中文回答", "slot": "language", "confidence": 0.98}},
  {{"category": "context", "content": "当前会话正在排查长期记忆方案", "confidence": 0.72}}
]
```
"""


def _strip_json_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        return re.sub(r"^```[a-zA-Z0-9_-]*\n?|\n?```$", "", content, flags=re.MULTILINE).strip()
    return content


def _sanitize_slot(slot: Optional[str]) -> Optional[str]:
    if not slot:
        return None
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", slot.strip()).strip("_").lower()
    return normalized or None


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.8
    return max(0.0, min(1.0, confidence))


def _build_memory_key(
    *,
    category: str,
    content: str,
    memory_kind: str,
    slot: Optional[str],
    record_id: int,
    index: int,
) -> str:
    if memory_kind == "profile" and slot:
        return f"slot:{slot}"
    elif memory_kind == "profile":
        raw_key = f"profile:{category}:{content}"
    else:
        return f"episode:{record_id}:{index}"
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()[:16]


def _normalize_memory_entry(
    entry: dict[str, Any],
    *,
    record_id: int,
    session_id: str,
    index: int,
) -> Optional[dict[str, Any]]:
    category = str(entry.get("category", "")).strip().lower()
    content = str(entry.get("content", "")).strip()
    if not content or category not in PROFILE_CATEGORIES.union(EPISODIC_CATEGORIES):
        return None

    memory_kind = "profile" if category in PROFILE_CATEGORIES else "episodic"
    slot = _sanitize_slot(entry.get("slot"))
    confidence = _coerce_confidence(entry.get("confidence"))
    if memory_kind == "profile":
        namespace = ("user", str(entry["user_id"]), memory_kind, category)
    else:
        namespace = ("user", str(entry["user_id"]), memory_kind, category)

    value = {
        "content": content,
        "category": category,
        "memory_kind": memory_kind,
        "confidence": confidence,
        "source_record_id": record_id,
    }
    ttl = None

    if memory_kind == "profile":
        if slot:
            value["slot"] = slot
    else:
        value["scope_type"] = DEFAULT_SCOPE_TYPE
        value["scope_id"] = session_id
        ttl = EPISODIC_MEMORY_TTL_SECONDS

    return {
        "namespace": namespace,
        "key": _build_memory_key(
            category=category,
            content=content,
            memory_kind=memory_kind,
            slot=slot,
            record_id=record_id,
            index=index,
        ),
        "value": value,
        "ttl": ttl,
    }


def _serialize_memory_item(item) -> dict[str, Any]:
    value = item.value or {}
    return {
        "category": value.get("category", "general"),
        "content": value.get("content", ""),
        "memory_kind": value.get("memory_kind"),
        "slot": value.get("slot"),
        "scope_type": value.get("scope_type"),
        "scope_id": value.get("scope_id"),
        "confidence": value.get("confidence"),
        "score": float(getattr(item, "score", 0.0) or 0.0),
    }


def _sort_profile_memories(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            PROFILE_CATEGORY_ORDER.get(item.get("category", ""), 99),
            item.get("slot") or "",
            item.get("content", ""),
        ),
    )


def _collect_profile_items(items: list[Any]) -> list[dict[str, Any]]:
    return [
        _serialize_memory_item(item)
        for item in items
        if item.value.get("category") in PROFILE_CATEGORIES
        and item.value.get("content")
    ]


async def extract_and_save_memories(
    store: BaseStore,
    *,
    record_id: int,
    user_id: str,
    session_id: str,
    question: str,
) -> int:
    """对话记录落库后，基于用户原话提取长期记忆。"""
    if not question or len(question.strip()) < 10:
        return 0

    try:
        llm = get_llm(temperature=0)
        prompt = EXTRACT_PROMPT.replace("{question}", question.strip()[:3000])
        result = await llm.ainvoke(prompt)
        content = result.content if hasattr(result, "content") else str(result)
        memories = json.loads(_strip_json_fence(content))
        if not isinstance(memories, list):
            return 0

        saved = 0
        for index, entry in enumerate(memories):
            if not isinstance(entry, dict):
                continue
            normalized = _normalize_memory_entry(
                {
                    **entry,
                    "user_id": str(user_id),
                },
                record_id=record_id,
                session_id=session_id,
                index=index,
            )
            if not normalized:
                continue
            await store.aput(
                normalized["namespace"],
                normalized["key"],
                normalized["value"],
                ttl=normalized["ttl"],
            )
            saved += 1

        if saved > 0:
            logger.info(
                "自动提取并保存 %s 条记忆 (user=%s, record=%s)",
                saved,
                user_id,
                record_id,
            )
        return saved
    except json.JSONDecodeError:
        logger.debug("记忆提取：LLM 返回非 JSON 内容，跳过")
        return 0
    except Exception as e:
        logger.warning(f"自动记忆提取失败: {e}", exc_info=True)
        return 0


async def retrieve_user_memories(
    store: BaseStore,
    user_id: str,
    query: Optional[str] = None,
    session_id: Optional[str] = None,
    profile_limit: int = PROFILE_MEMORY_LIMIT,
    episodic_limit: int = EPISODIC_MEMORY_LIMIT,
) -> dict[str, list[dict[str, Any]]]:
    """检索用户长期记忆，返回结构化的 profile / episodic 结果。"""
    memory_context: dict[str, list[dict[str, Any]]] = {"profile": [], "episodic": []}

    try:
        profile_results = await store.asearch(
            ("user", str(user_id), "profile"),
            filter={"memory_kind": "profile"},
            limit=profile_limit,
        )
        profile_items = _collect_profile_items(profile_results)
        if not profile_items:
            legacy_profile_results = await store.asearch(
                ("user", str(user_id)),
                limit=profile_limit,
            )
            profile_items = _collect_profile_items(legacy_profile_results)
        memory_context["profile"] = _sort_profile_memories(profile_items)[:profile_limit]

        if session_id:
            # 按时间排序获取当前会话的 episodic 记忆，避免 embedding 生成延迟
            episodic_results = await store.asearch(
                ("user", str(user_id), "episodic"),
                filter={
                    "memory_kind": "episodic",
                    "scope_type": DEFAULT_SCOPE_TYPE,
                    "scope_id": session_id,
                },
                limit=episodic_limit,
            )
            memory_context["episodic"] = [
                serialized
                for serialized in (
                    _serialize_memory_item(item) for item in episodic_results
                )
                if serialized["content"]
            ][:episodic_limit]

        return memory_context
    except Exception as e:
        logger.warning(f"检索用户记忆失败: {e}")
        return memory_context


def format_memory_context(memory_context: dict[str, list[dict[str, Any]]]) -> str:
    """将结构化记忆格式化成可注入 system prompt 的文本。"""
    lines = []

    if memory_context.get("profile"):
        lines.append("## 用户长期偏好/事实")
        lines.extend(
            f"- [{item.get('category', 'general')}] {item.get('content', '')}"
            for item in memory_context["profile"]
            if item.get("content")
        )

    if memory_context.get("episodic"):
        if lines:
            lines.append("")
        lines.append("## 当前会话背景")
        lines.extend(
            f"- [{item.get('category', 'context')}] {item.get('content', '')}"
            for item in memory_context["episodic"]
            if item.get("content")
        )

    return "\n".join(lines).strip()
