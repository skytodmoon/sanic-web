"""ask_user 工具 - 让 Agent 在执行过程中向用户提问并等待回答。

通过 LangGraph 的 interrupt() 机制实现暂停/恢复。
当 Agent 调用此工具时，执行流会暂停，后端将问题通过 SSE 发送给前端，
用户回答后通过 resume 端点恢复执行。
"""

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def ask_user(question: str) -> str:
    """向用户提问并等待回答。当你需要用户提供额外信息才能继续任务时使用此工具。

    使用场景：
    - 技能执行需要用户指定具体参数（如表名、时间范围等）
    - 需要用户确认操作方向
    - 需要用户补充缺失的关键信息

    Args:
        question: 要问用户的问题，应清晰具体，让用户容易理解和回答。

    Returns:
        用户的回答文本。
    """
    # interrupt() 会暂停 LangGraph 执行，将 question 发送到调用方
    # 调用方通过 Command(resume=answer) 恢复执行，answer 作为返回值
    answer = interrupt({"question": question})
    return answer
