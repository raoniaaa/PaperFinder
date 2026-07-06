"""LangGraph 图定义 —— 节点编排。"""

from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.nodes.fetch import fetch_papers
from src.nodes.filter import filter_papers
from src.nodes.reflect import reflect_papers
from src.nodes.digest import digest_papers
from src.nodes.store import store_papers
from src.nodes.output import output_result


def should_continue(state: AgentState) -> str:
    """条件路由：filter 之后，如果没有论文则直接跳到 output 发空报告。"""
    if len(state["filtered_papers"]) == 0:
        return "end"
    return "reflect"


def build_graph() -> StateGraph:
    """构建 LangGraph 工作流。"""

    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("fetch", fetch_papers)
    workflow.add_node("filter", filter_papers)
    workflow.add_node("reflect", reflect_papers)
    workflow.add_node("digest", digest_papers)
    workflow.add_node("store", store_papers)
    workflow.add_node("output", output_result)

    # 设置入口
    workflow.set_entry_point("fetch")

    # 连接边
    workflow.add_edge("fetch", "filter")

    # filter 之后条件分支：无论文则直接跳到输出，有论文进 reflect
    workflow.add_conditional_edges(
        "filter",
        should_continue,
        {"reflect": "reflect", "end": "output"},
    )

    workflow.add_edge("reflect", "digest")
    workflow.add_edge("digest", "store")
    workflow.add_edge("store", "output")
    workflow.add_edge("output", END)

    return workflow.compile()



