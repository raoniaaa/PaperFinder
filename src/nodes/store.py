"""Node 4: 持久化存储 —— SQLite + Chroma。"""

from src.state import AgentState
from src.storage.sqlite import paper_store
from src.storage.chroma import chroma_store
from src.utils.logger import logger


def store_papers(state: AgentState) -> AgentState:
    """将处理后的论文存入 SQLite 和 Chroma。"""
    logger.info("=" * 60)
    logger.info("💾 Node 4: 存储论文到本地知识库...")

    digested = state.get("digested_papers", [])
    if not digested:
        logger.info("   无论文需要存储，跳过")
        return state

    sqlite_count = 0
    chroma_count = 0

    for dp in digested:
        # SQLite 去重存储
        if paper_store.insert_paper(dp):
            sqlite_count += 1

        # Chroma 向量存储
        if chroma_store.add_paper(dp):
            chroma_count += 1

    logger.info(f"   ✅ SQLite 新增: {sqlite_count} 篇")
    logger.info(f"   ✅ Chroma 新增: {chroma_count} 篇（去重后）")
    logger.info(f"   📊 Chroma 总索引数: {chroma_store.count()}")

    state["stats"] = {
        **state.get("stats", {}),
        "sqlite_new": sqlite_count,
        "chroma_new": chroma_count,
        "chroma_total": chroma_store.count(),
    }

    return state
