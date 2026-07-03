"""Node 2: Agent A —— 论文相关性筛选。"""

from src.state import AgentState
from src.models.llm import llm
from src.config import (
    FILTER_BATCH_SIZE,
    FILTER_MIN_SCORE,
    GEO_HIGH_PRIORITY_KEYWORDS,
    GEO_MEDIUM_PRIORITY_KEYWORDS,
    GEO_NEGATIVE_KEYWORDS,
)
from src.utils.logger import logger

FILTER_SYSTEM_PROMPT = """你是「生成式引擎优化（Generative Engine Optimization, GEO）」领域的资深研究专家。
你的任务是评估一组论文摘要，判断它们与 GEO 领域的相关性并打分。

GEO 定义：研究如何优化内容以在 AI 搜索引擎（如 ChatGPT、Perplexity、Google AI Overviews 等）中获得更好的曝光、引用和排名。

高优先级主题（4-5分）：
- 生成式引擎优化（GEO）、答案引擎优化（AEO）
- AI 搜索引擎设计、对话式搜索系统
- LLM 驱动的搜索排序、检索增强生成（RAG）优化
- 内容在 AI 引擎中的可见性研究

中优先级主题（3分）：
- LLM 引用可靠性、来源归因
- 搜索结果偏见与公平性
- AI 生成答案中的幻觉缓解
- 结构化数据对 LLM 的影响
- 信息检索与生成式 AI 的交叉

低优先级/排除（1-2分）：
- 纯传统信息检索（不涉及生成式AI）
- 医疗影像、人脸识别、自动驾驶
- 纯理论数学推导
- 与搜索/AI引擎完全无关的通用 NLP/CV

请为每篇论文给出：
1. relevance_score: 1-5 的整数评分
2. relevance_reason: 一句话说明理由（中文）

严格按照以下 JSON 数组格式输出，不要输出其他内容：
{
  "papers": [
    {"arxiv_id": "论文ID", "relevance_score": 4, "relevance_reason": "理由"},
    ...
  ]
}"""


def _build_filter_user_message(abstracts_batch: list[tuple[str, str]]) -> str:
    """构造给 LLM 的批处理用户消息。"""
    lines = []
    for arxiv_id, title, abstract in abstracts_batch:
        # 截断过长摘要
        abstract_short = abstract[:800] if len(abstract) > 800 else abstract
        lines.append(f"---\nID: {arxiv_id}\n标题: {title}\n摘要: {abstract_short}")
    return "\n".join(lines)


def filter_papers(state: AgentState) -> AgentState:
    """Agent A: 分批调用 LLM 对论文相关性打分。"""
    logger.info("=" * 60)
    logger.info("🔍 Node 2: Agent A 开始筛选论文...")

    raw_papers = state.get("raw_papers", [])
    if not raw_papers:
        logger.info("   无论文需要筛选，跳过")
        state["filtered_papers"] = []
        state["stats"] = {**state.get("stats", {}), "filtered_count": 0}
        return state

    total = len(raw_papers)
    scored_papers = []

    # 分批处理
    for i in range(0, total, FILTER_BATCH_SIZE):
        batch = raw_papers[i : i + FILTER_BATCH_SIZE]
        batch_data = [(p.arxiv_id, p.title, p.abstract) for p in batch]

        logger.info(f"   处理批次 {i // FILTER_BATCH_SIZE + 1}, 共 {len(batch)} 篇...")

        try:
            user_msg = _build_filter_user_message(batch_data)
            result = llm.chat_json(
                system_prompt=FILTER_SYSTEM_PROMPT,
                user_message=user_msg,
                temperature=0.2,
            )

            # 解析 LLM 返回的评分
            scores = {}
            for item in result.get("papers", []):
                aid = item.get("arxiv_id", "")
                score = int(item.get("relevance_score", 0))
                reason = item.get("relevance_reason", "")
                scores[aid] = (score, reason)

            # 回填评分
            for paper in batch:
                if paper.arxiv_id in scores:
                    paper.relevance_score = scores[paper.arxiv_id][0]
                    paper.relevance_reason = scores[paper.arxiv_id][1]
                    scored_papers.append(paper)

        except Exception as e:
            logger.error(f"   ❌ 批次筛选失败: {e}")
            # 这批论文也给个默认低分，但不完全丢弃
            for paper in batch:
                paper.relevance_score = 1
                paper.relevance_reason = "LLM 调用异常，默认低分"
                scored_papers.append(paper)

    # 筛选: 评分 >= FILTER_MIN_SCORE
    filtered = [
        p for p in scored_papers if p.relevance_score >= FILTER_MIN_SCORE
    ]
    # 按评分降序排列
    filtered.sort(key=lambda p: p.relevance_score, reverse=True)

    logger.info(f"   ✅ 筛选完成: {len(filtered)}/{total} 篇通过（阈值 ≥{FILTER_MIN_SCORE}）")
    for p in filtered[:10]:
        logger.info(f"      [{p.relevance_score}分] {p.title[:80]}...")
        logger.info(f"         理由: {p.relevance_reason}")

    state["filtered_papers"] = filtered
    state["stats"] = {
        **state.get("stats", {}),
        "filtered_count": len(filtered),
        "total_fetched": total,
    }

    return state
