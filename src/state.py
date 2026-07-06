"""LangGraph 状态定义。"""

from typing import TypedDict, NotRequired
from src.models.paper import Paper, DigestedPaper


class AgentState(TypedDict):
    """多 Agent 流水线的全局状态。"""

    # 运行日期
    date: str

    # 原始抓取结果
    raw_papers: list[Paper]

    # 筛选后论文（含相关性评分）
    filtered_papers: list[Paper]

    # 深度梗概结果
    digested_papers: list[DigestedPaper]

    # 最终输出文本
    output_message: str

    # 统计信息
    stats: dict

    # 反思标记：是否已完成反思（最多一次）
    has_reflected: bool

    # ─── 飞书进度推送 ───
    # 接收消息的飞书用户 open_id（由 webhook/ws 注入，定时调度时为空不推送进度）
    feishu_chat_id: str
    # 接收消息的类型: "open_id"（私聊）或 "chat_id"（群聊）
    feishu_chat_type: str
    # 已发送的进度卡片 message_id（用于更新同一张卡片）
    feishu_card_message_id: str
