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

高优先级关键词（4-5分）：
{high_kw}

中优先级关键词（3分）：
{med_kw}

排除关键词（1-2分，出现以下词汇的论文与GEO无关）：
{neg_kw}

评分标准：
- 5分：论文核心直接研究 GEO/AEO 或 AI 搜索引擎的内容优化、排名或可见性
- 4分：论文与 RAG 优化、LLM 搜索排序、AI 搜索相关，且对 GEO 有明显启发
- 3分：论文涉及信息检索+生成式AI交叉、引用可靠性、幻觉缓解等，与 GEO 间接相关
- 2分：论文涉及传统信息检索但完全不涉及生成式 AI 或 LLM
- 1分：论文与搜索/信息检索/LLM应用均无关（如通用 NLP、CV、机器人等）

请为每篇论文给出：
1. relevance_score: 1-5 的整数评分
2. relevance_reason: 一句话说明理由（中文）

严格按照以下 JSON 格式输出，不要输出其他内容：
{{
  "papers": [
    {{"arxiv_id": "论文ID", "relevance_score": 4, "relevance_reason": "理由"}},
    ...
  ]
}}"""


def _build_filter_user_message(abstracts_batch: list[tuple[str, str]]) -> str:
    """构造给 LLM 的批处理用户消息。"""
    lines = []
    for arxiv_id, title, abstract in abstracts_batch:
        # 截断过长摘要
        abstract_short = abstract[:800] if len(abstract) > 800 else abstract
        lines.append(f"---\nID: {arxiv_id}\n标题: {title}\n摘要: {abstract_short}")
    return "\n".join(lines)


def _hard_filter_negative(text: str) -> bool:
    """硬过滤：标题或摘要包含负面关键词的直接排除。"""
    text_lower = text.lower()
    for kw in GEO_NEGATIVE_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False


def _hard_filter_positive(text: str) -> int:
    """硬校验：计算高优先级关键词命中数，辅助评分校准。"""
    text_lower = text.lower()
    hits = 0
    for kw in GEO_HIGH_PRIORITY_KEYWORDS:
        if kw.lower() in text_lower:
            hits += 1
    return hits


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

    # 构造带关键词的 system prompt
    prompt = FILTER_SYSTEM_PROMPT.format(
        high_kw=", ".join(GEO_HIGH_PRIORITY_KEYWORDS),
        med_kw=", ".join(GEO_MEDIUM_PRIORITY_KEYWORDS),
        neg_kw=", ".join(GEO_NEGATIVE_KEYWORDS),
    )

    total = len(raw_papers)
    negative_filtered_count = 0
    scored_papers = []

    # 分批处理
    for i in range(0, total, FILTER_BATCH_SIZE):
        batch = raw_papers[i : i + FILTER_BATCH_SIZE]

        # 第一层：负面关键词硬过滤
        filtered_batch = []
        for p in batch:
            if _hard_filter_negative(f"{p.title} {p.abstract}"):
                negative_filtered_count += 1
                continue
            filtered_batch.append(p)

        if not filtered_batch:
            continue

        batch_data = [(p.arxiv_id, p.title, p.abstract) for p in filtered_batch]
        logger.info(f"   处理批次 {i // FILTER_BATCH_SIZE + 1}, 共 {len(filtered_batch)} 篇（已过滤 {len(batch) - len(filtered_batch)} 篇）...")

        try:
            user_msg = _build_filter_user_message(batch_data)
            result = llm.chat_json(
                system_prompt=prompt,
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

            # 回填评分 + 第二层校验
            for paper in filtered_batch:
                if paper.arxiv_id in scores:
                    llm_score = scores[paper.arxiv_id][0]
                    reason = scores[paper.arxiv_id][1]

                    # 第二层：零高优先级关键词命中 + LLM 给 4+ 分 → 降级到 3
                    high_hits = _hard_filter_positive(f"{paper.title} {paper.abstract}")
                    if llm_score >= 4 and high_hits == 0:
                        llm_score = 3
                        reason = f"[降级] {reason}（未命中高优先级关键词）"

                    paper.relevance_score = llm_score
                    paper.relevance_reason = reason
                    scored_papers.append(paper)

        except Exception as e:
            logger.error(f"   ❌ 批次筛选失败: {e}")
            for paper in filtered_batch:
                paper.relevance_score = 1
                paper.relevance_reason = "LLM 调用异常，默认低分"
                scored_papers.append(paper)

    # 筛选: 评分 >= FILTER_MIN_SCORE
    filtered = [
        p for p in scored_papers if p.relevance_score >= FILTER_MIN_SCORE
    ]
    # 按评分降序排列
    filtered.sort(key=lambda p: p.relevance_score, reverse=True)

    logger.info(f"   ✅ 筛选完成: {len(filtered)}/{total} 篇通过（阈值 ≥{FILTER_MIN_SCORE}），硬过滤 {negative_filtered_count} 篇")
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
