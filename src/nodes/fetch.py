"""Node 1: arXiv API 论文抓取（带 429 重试）。"""

import time
from datetime import datetime, timedelta
import arxiv
from src.state import AgentState
from src.models.paper import Paper
from src.config import ARXIV_CATEGORIES, ARXIV_MAX_RESULTS_PER_CATEGORY, ARXIV_DAYS_BACK
from src.utils.logger import logger

# arXiv 429 限流重试配置
ARXIV_RETRY_MAX = 5        # 最大重试次数
ARXIV_RETRY_BASE_WAIT = 10 # 首次等待秒数，逐次翻倍


def _build_query(target_date: str) -> str:
    """构建 arXiv 查询：按分类号 + 指定日期。"""
    categories_or = " OR ".join(f"cat:{cat}" for cat in ARXIV_CATEGORIES)
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_str = dt.strftime("%Y%m%d")
    query = f"({categories_or}) AND submittedDate:[{date_str} TO {date_str}]"
    return query


def _is_rate_limit(err: Exception) -> bool:
    """判断异常是否为限流（429/503）。"""
    msg = str(err)
    return "429" in msg or "503" in msg


def fetch_papers(state: AgentState) -> AgentState:
    """从 arXiv API 抓取指定日期论文（带 429 重试）。"""
    logger.info("=" * 60)
    logger.info("📡 Node 1: 开始从 arXiv 抓取论文...")

    target_date = state.get("date", datetime.now().strftime("%Y-%m-%d"))
    query = _build_query(target_date)

    logger.info(f"   目标日期: {target_date}")
    logger.info(f"   查询语句: {query}")

    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=ARXIV_MAX_RESULTS_PER_CATEGORY * len(ARXIV_CATEGORIES),
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )

    papers: list[Paper] = []
    seen_ids: set[str] = set()

    # 抓取阶段不发飞书消息，进度由 filter 节点用卡片统一展示

    last_error = ""
    for attempt in range(1, ARXIV_RETRY_MAX + 1):
        try:
            it = client.results(search)
            for result in it:
                arxiv_id = result.get_short_id()
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
            break

        except Exception as e:
            last_error = str(e)
            if _is_rate_limit(e) and attempt < ARXIV_RETRY_MAX:
                wait = ARXIV_RETRY_BASE_WAIT * (2 ** (attempt - 1))
                logger.warning(f"   ⚠️ arXiv 限流，{wait}s 后重试 ({attempt}/{ARXIV_RETRY_MAX})...")
                time.sleep(wait)
                continue
            else:
                logger.error(f"   ❌ arXiv API 抓取失败 (尝试 {attempt}/{ARXIV_RETRY_MAX}): {last_error}")
                papers = []
                break

    if not papers and last_error:
        logger.warning(f"   ⚠️ arXiv 抓取失败: {last_error[:80]}")

    state["raw_papers"] = papers
    state["date"] = target_date
    state["stats"] = {**state.get("stats", {}), "raw_count": len(papers)}

    return state
