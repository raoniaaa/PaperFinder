"""LangGraph 状态定义。"""

from typing import TypedDict
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
