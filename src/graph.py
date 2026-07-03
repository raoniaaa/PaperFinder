"""LangGraph 图定义 —— 节点编排。"""

from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.nodes.fetch import fetch_papers
from src.nodes.filter import filter_papers
from src.nodes.digest import digest_papers
from src.nodes.store import store_papers
from src.nodes.output import output_result


def should_continue(state: AgentState) -> str:
    """条件路由：如果筛选后无有效论文则直接结束。"""
    if len(state["filtered_papers"]) == 0:
        return "end"
    return "digest"


def build_graph() -> StateGraph:
    """构建 LangGraph 工作流。"""

    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("fetch", fetch_papers)
    workflow.add_node("filter", filter_papers)
    workflow.add_node("digest", digest_papers)
    workflow.add_node("store", store_papers)
    workflow.add_node("output", output_result)

    # 设置入口
    workflow.set_entry_point("fetch")

    # 连接边
    workflow.add_edge("fetch", "filter")

    # filter 之后条件分支
    workflow.add_conditional_edges(
        "filter",
        should_continue,
        {
            "digest": "digest",
            "end": END,
        },
    )

    workflow.add_edge("digest", "store")
    workflow.add_edge("store", "output")
    workflow.add_edge("output", END)

    return workflow.compile()


# 编译好的 graph 实例
graph = build_graph()
