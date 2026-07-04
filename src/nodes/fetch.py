"""Node 1: arXiv API 论文抓取。"""

from datetime import datetime, timedelta
import arxiv
from src.state import AgentState
from src.models.paper import Paper
from src.config import ARXIV_CATEGORIES, ARXIV_MAX_RESULTS_PER_CATEGORY, ARXIV_DAYS_BACK
from src.utils.logger import logger


def _build_query(target_date: str) -> str:
    """构建 arXiv 查询：按分类号 + 指定日期。"""
    # 分类号 OR 拼接
    categories_or = " OR ".join(f"cat:{cat}" for cat in ARXIV_CATEGORIES)

    # 按指定日期搜索（单日范围）
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_str = dt.strftime("%Y%m%d")
    query = f"({categories_or}) AND submittedDate:[{date_str} TO {date_str}]"
    return query


def fetch_papers(state: AgentState) -> AgentState:
    """从 arXiv API 抓取指定日期论文。"""
    logger.info("=" * 60)
    logger.info("📡 Node 1: 开始从 arXiv 抓取论文...")

    target_date = state.get("date", datetime.now().strftime("%Y-%m-%d"))
    query = _build_query(target_date)

    logger.info(f"   目标日期: {target_date}")
    logger.info(f"   查询语句: {query}")

    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=ARXIV_MAX_RESULTS_PER_CATEGORY * len(ARXIV_CATEGORIES),
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )

        papers: list[Paper] = []
        seen_ids: set[str] = set()

        for result in client.results(search):
            arxiv_id = result.get_short_id()

            # 去重（同一篇论文可能出现在多个分类）
            if arxiv_id in seen_ids:
                continue
            seen_ids.add(arxiv_id)

            paper = Paper(
                arxiv_id=arxiv_id,
                title=result.title or "",
                authors=[a.name for a in result.authors],
                abstract=result.summary.replace("\n", " ").strip() if result.summary else "",
                published_date=result.published.strftime("%Y-%m-%d") if result.published else "",
                pdf_url=result.pdf_url or "",
                primary_category=result.primary_category or "",
            )
            papers.append(paper)

        logger.info(f"   ✅ 抓取完成: 共获取 {len(papers)} 篇论文（已去重）")

    except Exception as e:
        logger.error(f"   ❌ arXiv API 抓取失败: {e}")
        papers = []

    state["raw_papers"] = papers
    state["date"] = target_date
    state["stats"] = {**state.get("stats", {}), "raw_count": len(papers)}

    return state
