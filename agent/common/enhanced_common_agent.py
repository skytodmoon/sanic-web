"""
EnhancedCommonAgent - 基于 DeepAgents 的增强通用问答智能体

支持 Skill + MCP + 多轮对话 + 思考可视化
"""

import asyncio
import json
import logging
import os
import traceback
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from agent.deepagent.tools.tool_call_manager import get_tool_call_manager
from langgraph.checkpoint.memory import InMemorySaver
from common.llm_util import get_llm
from common.minio_util import MinioUtils
from constants.code_enum import DataTypeEnum, IntentEnum
from services.user_service import add_user_record, decode_jwt_token
logger = logging.getLogger(__name__)

current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # Aix-DB 项目根目录
agent_workspace_dir = current_dir / "agent_workspace"
agent_sessions_dir = agent_workspace_dir / "sessions"
minio_utils = MinioUtils()


# ==================== 阶段枚举与追踪 ====================


class Phase(Enum):
    """Agent 执行阶段"""

    PLANNING = "planning"
    EXECUTION = "execution"
    SUB_AGENT = "sub_agent"
    REPORTING = "reporting"


@dataclass
class PhaseTracker:
    """阶段追踪器：管理 <details> 标签的开关状态"""

    current_phase: Phase = Phase.PLANNING
    planning_opened: bool = False
    execution_opened: bool = False
    reporting_opened: bool = False
    current_node: str = ""
    has_tool_called: bool = False
    has_sent_content: bool = False
    current_tool_name: str = ""
    current_tool_output: list = None

    def __post_init__(self):
        if self.current_tool_output is None:
            self.current_tool_output = []


# ==================== 样式模板 ====================

SECTION_CLOSE = "\n</details>\n\n"

# 执行区：折叠，包裹工具调用过程
EXECUTION_SECTION_OPEN = (
    '<details style="margin:6px 0;padding:6px 12px;'
    'border-left:3px solid #42a5f5;border-radius:3px;color:#666">\n'
    '<summary style="cursor:pointer;font-weight:600;color:#1565c0">'
    '⚡ 工具调用过程</summary>\n\n'
)

# 工具调用标签（紧凑行内）
TOOL_LABEL = '<span style="color:#1976d2;font-size:13px">🔧 **{name}**</span>\n\n'

# Todo 状态图标
TODO_STATUS_ICONS = {"pending": "○", "in_progress": "◉", "completed": "✓"}

TODO_SECTION_OPEN = (
    '<details open style="margin:6px 0;padding:6px 12px;'
    'border-left:3px solid #66bb6a;border-radius:3px;color:#666">\n'
    '<summary style="cursor:pointer;font-weight:600;color:#2e7d32">'
    '📋 任务计划</summary>\n\n'
)


def _format_tool_label(tool_name: str) -> str:
    """工具调用标签（直接可见）"""
    return TOOL_LABEL.format(name=tool_name)


def _format_todos(todos: list) -> str:
    """将 todo 列表格式化为带状态图标的文本"""
    lines = []
    for t in todos:
        icon = TODO_STATUS_ICONS.get(t.get("status", "pending"), "○")
        content = t.get("content", "")
        lines.append(f"  {icon} {content}")
    return TODO_SECTION_OPEN + "\n".join(lines) + SECTION_CLOSE


# ==================== EnhancedCommonAgent 主类 ====================


class EnhancedCommonAgent:
    """基于 DeepAgents 的增强通用问答智能体，支持 Skill + MCP"""

    DEFAULT_RECURSION_LIMIT = 150
    DEFAULT_LLM_TIMEOUT = 15 * 60
    STREAM_KEEPALIVE_INTERVAL = 25
    TASK_TIMEOUT = 30 * 60

    def __init__(self):
        self.checkpointer = InMemorySaver()
        self.memory_store = None
        self.running_tasks = {}
        self.tool_manager = get_tool_call_manager()
        self.ENABLE_TRACING = os.getenv("LANGFUSE_TRACING_ENABLED", "false").lower() == "true"

    # ==================== MCP 客户端 ====================

    def _init_mcp_client(self):
        """从环境变量初始化 MCP 客户端"""
        mcp_url = os.environ.get("MCP_HUB_COMMON_QA_GROUP_URL")
        if not mcp_url:
            logger.warning("MCP_HUB_COMMON_QA_GROUP_URL 未配置，MCP 工具将不可用")
            return None

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            client = MultiServerMCPClient(
                {
                    "mcp-hub": {
                        "url": mcp_url,
                        "transport": "streamable_http",
                    },
                }
            )
            return client
        except Exception as e:
            logger.warning(f"初始化 MCP 客户端失败: {e}")
            return None

    async def _get_mcp_tools(self):
        """动态获取 MCP 工具，不可用时降级为空列表"""
        client = self._init_mcp_client()
        if client is None:
            return []
        try:
            tools = await client.get_tools()
            return tools
        except Exception as e:
            logger.warning(f"获取 MCP 工具失败: {e}")
            return []

    # ==================== 文件下载 ====================

    def _download_files_to_workspace(self, file_list: list) -> list:
        """将 MinIO 中的原始文件下载到项目级工作目录，返回文件信息列表"""
        workspace_dir = agent_workspace_dir
        workspace_dir.mkdir(exist_ok=True)

        downloaded_files = []
        for file_info in file_list:
            source_key = file_info.get("source_file_key", "")
            if not source_key:
                continue
            # 提取原始文件名（去掉 uuid__ 前缀）
            original_name = source_key.split("__", 1)[-1] if "__" in source_key else source_key
            local_path = workspace_dir / original_name

            # 通过 MinIO 下载原始文件
            if minio_utils.download_file(source_key, str(local_path)):
                downloaded_files.append(
                    {
                        "original_name": original_name,
                        "local_path": str(local_path),
                        "source_key": source_key,
                    }
                )

        return downloaded_files

    # ==================== Agent 创建 ====================

    async def _create_agent(
        self,
        system_prompt: Optional[str] = None,
        mcp_tools: Optional[list] = None,
        session_workdir: Optional[Path] = None,
    ):
        """创建 deep agent 实例

        Args:
            mcp_tools: 预获取的 MCP 工具列表，为 None 时内部获取
            session_workdir: session 级工作目录，优先于全局 agent_workspace_dir
        """
        if mcp_tools is None:
            mcp_tools = await self._get_mcp_tools()

        from services.skill_service import SkillService

        skill_paths = str(current_dir / "skills")

        model = get_llm(timeout=self.DEFAULT_LLM_TIMEOUT)
        workdir = session_workdir or agent_workspace_dir
        workdir.mkdir(parents=True, exist_ok=True)
        return create_deep_agent(
            model=model,
            tools=mcp_tools,
            system_prompt=system_prompt,
            memory=[str(current_dir / "AGENTS.md")],
            skills=[skill_paths],
            backend=LocalShellBackend(
                root_dir=str(workdir),
                inherit_env=True,
                timeout=120
            ),
            # middleware=[
            #         # 开启上下文总结压缩
            #         SummarizationMiddleware(
            #             model=model,
            #             max_tokens_before_summary=4000,
            #             messages_to_keep=20,
            #         ),
            #         # 通过修剪、总结或清除工具使用来管理对话上下文。
            #         # 需要定期清理上下文的长对话
            #         # 从上下文中删除失败的工具尝试
            #         ContextEditingMiddleware(
            #             edits=[
            #                 ClearToolUsesEdit(trigger=10000),  # Clear old tool uses
            #             ],
            #         ),
            #     ],
            checkpointer=self.checkpointer,
        )

    # ==================== SSE 响应工具 ====================

    @staticmethod
    def _create_response(
        content: str,
        message_type: str = "continue",
        data_type: str = DataTypeEnum.ANSWER.value[0],
    ) -> str:
        """封装 SSE 响应结构"""
        res = {
            "data": {"messageType": message_type, "content": content},
            "dataType": data_type,
        }
        return "data:" + json.dumps(res, ensure_ascii=False) + "\n\n"

    async def _safe_write(self, response, content: str, message_type: str = "continue") -> bool:
        """安全地写入 SSE 响应，连接断开时返回 False"""
        try:
            await response.write(self._create_response(content, message_type))
            if hasattr(response, "flush"):
                await response.flush()
            return True
        except Exception as e:
            if self._is_connection_error(e):
                logger.info(f"客户端连接已断开: {type(e).__name__}")
                return False
            raise

    @staticmethod
    def _is_connection_error(exception: Exception) -> bool:
        """判断是否是连接断开相关的异常"""
        error_type = type(exception).__name__
        error_msg = str(exception).lower()
        connection_error_types = [
            "ConnectionClosed",
            "ConnectionResetError",
            "BrokenPipeError",
            "ConnectionError",
            "OSError",
        ]
        connection_error_keywords = [
            "connection closed",
            "connection reset",
            "broken pipe",
            "client disconnected",
            "connection aborted",
            "transport closed",
        ]
        if error_type in connection_error_types:
            return True
        for keyword in connection_error_keywords:
            if keyword in error_msg:
                return True
        return False

    async def _send_phase_progress(
        self, response, phase: Phase, status: str, progress_id: str
    ):
        """发送 phase 切换的 step_progress 事件 (t14)"""
        phase_map = {
            Phase.PLANNING: ("planning", "🧠 思考与规划"),
            Phase.EXECUTION: ("execution", "⚙️ 执行中"),
            Phase.REPORTING: ("reporting", "📋 总结回答"),
        }
        step, step_name = phase_map.get(phase, ("unknown", "未知阶段"))
        progress_data = {
            "type": "step_progress",
            "step": step,
            "stepName": step_name,
            "status": status,
            "progressId": progress_id,
        }
        formatted = {
            "data": progress_data,
            "dataType": DataTypeEnum.STEP_PROGRESS.value[0],
        }
        await response.write(
            "data:" + json.dumps(formatted, ensure_ascii=False) + "\n\n"
        )

    @staticmethod
    def _extract_text(content) -> str:
        """从消息内容中提取文本"""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    parts.append(part)
            return "".join(parts)
        return str(content) if content else ""

    # ==================== 流式响应处理 ====================

    async def _stream_response(
        self, agent, config, query, response, session_id, answer_collector
    ):
        """
        流式响应处理 - 实时输出：
        1. AI 文本实时输出（不缓冲）
        2. 工具调用过程折叠在 <details> 中，但结果直接展示
        3. 工具执行后的回答直接输出
        """
        import uuid

        tracker = PhaseTracker()
        last_keepalive = asyncio.get_event_loop().time()
        progress_id = str(uuid.uuid4())

        # 辅助：统一写入（发送到前端 + 收集到 answer_collector）
        async def write_and_collect(content: str):
            await self._safe_write(response, content)
            answer_collector.append(content)

        async def enter_execution():
            """首次工具调用时切换到执行阶段"""
            if tracker.current_phase == Phase.EXECUTION:
                return
            tracker.current_phase = Phase.EXECUTION
            tracker.has_tool_called = True
            await self._send_phase_progress(
                response, Phase.EXECUTION, "start", progress_id
            )
            # 打开折叠的工具调用过程区域
            await write_and_collect(EXECUTION_SECTION_OPEN)
            tracker.execution_opened = True

        async def close_execution_enter_reporting():
            """关闭执行区，进入回答阶段"""
            if tracker.execution_opened:
                await write_and_collect(SECTION_CLOSE)
                tracker.execution_opened = False
            tracker.current_phase = Phase.REPORTING
            await self._send_phase_progress(
                response, Phase.REPORTING, "start", progress_id
            )

        try:
            await self._send_phase_progress(
                response, Phase.PLANNING, "start", progress_id
            )

            async for mode, chunk in agent.astream(
                {"messages": [{"role": "user", "content": query}]},
                config,
                stream_mode=["messages", "updates"],
            ):
                # 检查是否已取消
                if self.running_tasks.get(session_id, {}).get("cancelled"):
                    await self._safe_write(
                        response, "\n> 这条消息已停止", "info",
                    )
                    await self._safe_write(response, "", "end")
                    return

                current_time = asyncio.get_event_loop().time()

                # 保活
                if current_time - last_keepalive >= self.STREAM_KEEPALIVE_INTERVAL:
                    try:
                        await response.write(": keepalive\n\n")
                        if hasattr(response, "flush"):
                            await response.flush()
                        last_keepalive = current_time
                    except Exception:
                        pass

                # ===== updates 模式：捕获 todos 更新 =====
                if mode == "updates":
                    if isinstance(chunk, dict):
                        for node_name, node_output in chunk.items():
                            if not isinstance(node_output, dict):
                                continue
                            todos = node_output.get("todos")
                            if todos and isinstance(todos, list):
                                await write_and_collect(_format_todos(todos))
                    continue

                # ===== messages 模式 =====
                message_chunk, metadata = chunk
                langgraph_node = metadata.get("langgraph_node", "")

                text = (
                    self._extract_text(message_chunk.content)
                    if hasattr(message_chunk, "content")
                    else ""
                )

                # ===== 工具调用节点：折叠在执行区内 =====
                if langgraph_node == "tools":
                    tool_name = getattr(message_chunk, "name", None) or "未知工具"

                    # 跳过 write_todos（已通过 updates 展示）
                    if tool_name == "write_todos":
                        continue

                    await enter_execution()

                    # 工具切换时输出标签
                    if tool_name != tracker.current_tool_name:
                        tracker.current_tool_name = tool_name
                        await write_and_collect(_format_tool_label(tool_name))

                    if text:
                        await write_and_collect(text)
                    continue

                # ===== 非工具节点的 AI 文本 =====
                if not text:
                    continue

                # 从执行阶段切换到回答阶段
                if tracker.current_phase == Phase.EXECUTION:
                    tracker.current_tool_name = ""
                    await close_execution_enter_reporting()

                # 直接实时输出（无论是 PLANNING 还是 REPORTING）
                await write_and_collect(text)

            # ===== 流结束清理 =====
            if tracker.execution_opened:
                await write_and_collect(SECTION_CLOSE)
                tracker.execution_opened = False

        except asyncio.CancelledError:
            await self._safe_write(response, "\n> 这条消息已停止", "info")
            await self._safe_write(response, "", "end")
        except Exception as e:
            logger.error(f"流式响应异常: {e}", exc_info=True)
            await self._safe_write(
                response,
                f"[ERROR] 响应异常: {str(e)[:100]}",
                "error",
            )

    # ==================== 核心运行方法 ====================

    async def run_agent(
        self,
        query: str,
        response,
        session_id: Optional[str] = None,
        uuid_str: str = None,
        user_token=None,
        file_list: dict = None,
    ):
        """
        运行增强智能体
        """
        file_as_markdown = ""
        downloaded_files = []
        if file_list:
            # 下载原始文件到本地
            downloaded_files = self._download_files_to_workspace(file_list)
            # 同时保留文本内容
            file_as_markdown = minio_utils.get_files_content_as_markdown(file_list) # type: ignore

        # JWT 解码获取用户信息
        user_dict = await decode_jwt_token(user_token)
        task_id = user_dict["id"]
        task_context = {"cancelled": False}
        self.running_tasks[task_id] = task_context

        # 格式化查询
        formatted_query = query
        if downloaded_files:
            file_info_text = "\n".join(
                f"- 文件名: {f['original_name']}, 本地路径: {f['local_path']}"
                for f in downloaded_files
            )
            formatted_query = f"{query}\n\n用户上传的文件（已下载到本地）：\n{file_info_text}"

        if file_as_markdown:
            formatted_query += f"\n\n文件文本内容：\n{file_as_markdown}"

        # 重置工具管理器
        self.tool_manager.reset_session(task_id)

        try:
            t02_answer_data = []

            # 使用 session_id 作为 thread_id
            thread_id = session_id if session_id else "default_thread"

            # session 级工作目录
            session_workdir = agent_sessions_dir / thread_id
            session_workdir.mkdir(parents=True, exist_ok=True)

            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "user_id": str(task_id),
                },
                "recursion_limit": self.DEFAULT_RECURSION_LIMIT,
            }
            if self.ENABLE_TRACING:
                from langfuse.langchain import CallbackHandler
                config["callbacks"] = [CallbackHandler()]
                config["metadata"] = {"langfuse_session_id": session_id}

            mcp_tools = await self._get_mcp_tools()

            # 创建 agent
            agent = await self._create_agent(
                system_prompt=None,
                mcp_tools=mcp_tools,
                session_workdir=session_workdir,
            )

            # 带超时保护的任务
            task = asyncio.create_task(
                self._stream_response(
                    agent, config, formatted_query, response, task_id, t02_answer_data
                )
            )

            try:
                if self.ENABLE_TRACING:
                    from langfuse import get_client
                    langfuse = get_client()
                    with langfuse.start_as_current_observation(
                        input=query,
                        as_type="agent",
                        name="通用问答",
                    ) as rootspan:
                        rootspan.update_trace(
                            session_id=session_id, user_id=str(task_id)
                        )
                        await asyncio.wait_for(task, timeout=self.TASK_TIMEOUT)
                else:
                    await asyncio.wait_for(task, timeout=self.TASK_TIMEOUT)
            except asyncio.TimeoutError:
                task.cancel()
                await self._safe_write(
                    response,
                    "\n> 任务超时（30分钟），已自动停止",
                    "info",
                )
                await self._safe_write(response, "", "end")
                logger.warning(f"任务 {task_id} 超时")

            # 保存对话记录（未取消且正常结束）
            record_id = None
            if task_context.get("cancelled") is not True and uuid_str and session_id:
                try:
                    record_id = await add_user_record(
                        uuid_str,
                        session_id,
                        query,
                        t02_answer_data,
                        {},
                        IntentEnum.COMMON_QA.value[0],
                        user_token,
                        file_list,
                    )
                    logger.info(f"add_user_record 返回 record_id={record_id}, uuid_str={uuid_str}, session_id={session_id}")
                except Exception as e:
                    logger.error(f"保存对话记录失败: {e}", exc_info=True)

            # 发送结束标记
            if not task_context.get("cancelled"):
                # 扫描 session 工作目录，收集生成的文件
                if session_workdir.exists():
                    generated_files = []
                    for f in session_workdir.iterdir():
                        if f.is_file() and not f.name.startswith("."):
                            # 返回相对于 workspace 的路径，供下载接口使用
                            rel_path = str(f.relative_to(agent_workspace_dir))
                            generated_files.append({
                                "name": f.name,
                                "path": rel_path,
                                "size": f.stat().st_size,
                            })
                    if generated_files:
                        file_list_data = {
                            "data": {"files": generated_files},
                            "dataType": DataTypeEnum.GENERATED_FILES.value[0],
                        }
                        await response.write("data:" + json.dumps(file_list_data, ensure_ascii=False) + "\n\n")

                await response.write(
                    "data:"
                    + json.dumps(
                        {
                            "data": "DONE",
                            "dataType": DataTypeEnum.STREAM_END.value[0],
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

        except asyncio.CancelledError:
            await self._safe_write(response, "\n> 这条消息已停止", "info")
            await response.write(
                "data:"
                + json.dumps(
                    {"data": "DONE", "dataType": DataTypeEnum.STREAM_END.value[0]},
                    ensure_ascii=False,
                )
                + "\n\n"
            )
        except Exception as e:
            print(f"[ERROR] Agent运行异常: {e}")
            traceback.print_exception(e)
            await self._safe_write(
                response,
                f"[ERROR] 智能体运行异常: {str(e)[:200]}",
                "error",
            )
        finally:
            # 仅清理上传的临时文件，保留 agent 生成的文件供用户获取
            for f in downloaded_files:
                try:
                    Path(f["local_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]

    async def cancel_task(self, task_id: str) -> bool:
        """取消指定的任务"""
        if task_id in self.running_tasks:
            self.running_tasks[task_id]["cancelled"] = True
            logger.info(f"任务 {task_id} 已标记取消")
            return True
        return False
