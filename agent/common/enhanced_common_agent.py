"""
EnhancedCommonAgent - 基于 DeepAgents 的增强通用问答智能体

支持 Skill + MCP + 多轮对话 + 思考可视化
"""

import asyncio
import json
import logging
import os
import shutil
import traceback
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langgraph.checkpoint.memory import InMemorySaver

from agent.deepagent.tools.tool_call_manager import get_tool_call_manager
from common.llm_util import get_llm
from common.minio_util import MinioUtils
from constants.code_enum import DataTypeEnum, IntentEnum
from services.user_service import add_user_record, decode_jwt_token

logger = logging.getLogger(__name__)

current_dir = Path(__file__).parent
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
    current_node: str = ""
    has_tool_called: bool = False
    has_sent_content: bool = False


# ==================== <details> 标签模板 ====================

THINKING_SECTION_OPEN = (
    '<details open style="margin:8px 0;padding:8px 12px;background:#f8f9fa;'
    "border-left:3px solid #4a90d9;border-radius:4px;font-size:14px;color:#555"
    '">\n'
    '<summary style="cursor:pointer;font-weight:600;color:#333">'
    "🧠 思考与规划</summary>\n\n"
)

SECTION_CLOSE = "\n</details>\n\n"


# ==================== EnhancedCommonAgent 主类 ====================


class EnhancedCommonAgent:
    """基于 DeepAgents 的增强通用问答智能体，支持 Skill + MCP"""

    DEFAULT_RECURSION_LIMIT = 150
    DEFAULT_LLM_TIMEOUT = 15 * 60
    STREAM_KEEPALIVE_INTERVAL = 25
    TASK_TIMEOUT = 30 * 60

    def __init__(self):
        self.checkpointer = InMemorySaver()
        self.running_tasks = {}
        self.tool_manager = get_tool_call_manager()

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
        """将 MinIO 中的原始文件下载到本地工作目录，返回文件信息列表"""
        workspace_dir = current_dir / "workspace"
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

    async def _create_agent(self, selected_skills=None):
        """创建 deep agent 实例"""
        mcp_tools = await self._get_mcp_tools()
        from services.skill_service import SkillService

        skill_paths = SkillService.get_enabled_skill_paths(selected_skills)

        model = get_llm(timeout=self.DEFAULT_LLM_TIMEOUT)
        return create_deep_agent(
            model=model,
            tools=mcp_tools,
            memory=[str(current_dir / "AGENTS.md")],
            skills=skill_paths if skill_paths else None,
            backend=LocalShellBackend(
                root_dir=str(current_dir),
                inherit_env=True,
                timeout=120.0,
            ),
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
        """流式响应处理"""
        tracker = PhaseTracker()
        last_keepalive = asyncio.get_event_loop().time()
        langgraph_node = ""

        try:
            async for message_chunk, metadata in agent.astream(
                {"messages": [{"role": "user", "content": query}]},
                config,
                stream_mode="messages",
            ):
                # 检查是否已取消
                if self.running_tasks.get(session_id, {}).get("cancelled"):
                    await self._safe_write(
                        response,
                        "\n> 这条消息已停止",
                        "info",
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

                # 获取当前节点名
                langgraph_node = metadata.get("langgraph_node", "")

                # 检测阶段
                if not tracker.has_tool_called and langgraph_node == "tools":
                    tracker.has_tool_called = True
                    tracker.current_phase = Phase.EXECUTION
                    # 关闭思考区
                    if tracker.planning_opened:
                        await self._safe_write(response, SECTION_CLOSE)
                        tracker.planning_opened = False

                # 提取文本内容
                text = self._extract_text(message_chunk.content) if hasattr(message_chunk, "content") else ""

                if not text:
                    continue

                # 工具调用节点
                if langgraph_node == "tools":
                    tool_name = getattr(message_chunk, "name", None) or "未知工具"
                    tool_output = f"> 调用工具: {tool_name}\n\n"
                    await self._safe_write(response, tool_output)
                    answer_collector.append(tool_output)
                    continue

                # 打开思考区（首次非工具输出）
                if tracker.current_phase == Phase.PLANNING and not tracker.planning_opened:
                    await self._safe_write(response, THINKING_SECTION_OPEN)
                    tracker.planning_opened = True

                # 流式输出内容
                if text:
                    await self._safe_write(response, text)
                    answer_collector.append(text)

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
        selected_skills: list = None,
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
            file_as_markdown = minio_utils.get_files_content_as_markdown(file_list)

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

            # 创建 agent
            agent = await self._create_agent(selected_skills)

            # 使用 session_id 作为 thread_id
            thread_id = session_id if session_id else "default_thread"
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": self.DEFAULT_RECURSION_LIMIT,
            }

            # 带超时保护的任务
            task = asyncio.create_task(
                self._stream_response(
                    agent, config, formatted_query, response, task_id, t02_answer_data
                )
            )

            try:
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
            if task_context.get("cancelled") is not True and uuid_str and session_id:
                try:
                    await add_user_record(
                        uuid_str,
                        session_id,
                        query,
                        t02_answer_data,
                        {},
                        IntentEnum.COMMON_QA.value[0],
                        user_token,
                        file_list,
                    )
                except Exception as e:
                    logger.error(f"保存对话记录失败: {e}")

            # 发送结束标记
            if not task_context.get("cancelled"):
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
            # 清理本地工作目录中的临时文件
            workspace_dir = current_dir / "workspace"
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir, ignore_errors=True)
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]

    async def cancel_task(self, task_id: str) -> bool:
        """取消指定的任务"""
        if task_id in self.running_tasks:
            self.running_tasks[task_id]["cancelled"] = True
            logger.info(f"任务 {task_id} 已标记取消")
            return True
        return False
