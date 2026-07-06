"""Node 2.5: 反思节点 —— 在筛选后二次校验论文是否真正与 GEO 强相关。"""

from src.state import AgentState
from src.models.llm import llm
from src.utils.logger import logger
from src.config import GEO_HIGH_PRIORITY_KEYWORDS

REFLECT_SYSTEM_PROMPT = """你是「生成式引擎优化（GEO）」领域的审稿专家。对初筛通过的论文进行严格二次反思。

GEO 严格定义：研究如何优化内容以在 AI 搜索引擎中获得更好的可见性、引用和排名。

★ 核心判断标准 ★：
论文的**核心研究问题**是否直接关于 AI 搜索引擎中的内容优化？
如果论文只是"可以用在 AI 搜索中"、"对 GEO 有启发"，而不是"研究 AI 搜索中的内容优化"，应判定为 drop。

★ 明确应 drop 的情况 ★：
- 论文做的是通用 RAG 优化（retrieval 质量、chunking 策略等），不专门针对 AI 搜索引擎场景 → drop
- 论文做的是 LLM 幻觉缓解/归因，但从 NLP 视角而非内容发布者/SEO 视角 → drop
- 论文用到了 LLM/RAG 但场景是医疗、教育、代码等，与搜索/内容可见性无关 → drop
- 论文是纯方法论改进（如 prompt 优化、few-shot 策略），不涉及搜索 → drop

★ 明确应 keep 的情况 ★：
- 论文直接研究 AI 搜索引擎中的内容排名/引用/可见性 → keep
- 论文研究 AI Overviews / Answer Engine 中的内容呈现机制 → keep
- 论文研究 LLM 如何选择/排序外部信息来源（从内容发布者视角） → keep

对每篇论文给出：
- verdict: "keep" 或 "drop"
- reason: 一句话（中文），必须明确指出论文核心研究问题是什么

JSON 格式：
{{
  "reviews": [
    {{"arxiv_id": "论文ID", "verdict": "keep", "reason": "理由"}},
    ...
  ]
}}"""


def reflect_papers(state: AgentState) -> AgentState:
    """反思校验：对筛选通过的论文做二次评估，剔除弱相关论文。"""
    logger.info("=" * 60)
    logger.info("🪞 Node 2.5: 反思校验 —— 二次评估论文与 GEO 的关联度...")

    # 只反思一次
    if state.get("has_reflected", False):
        logger.info("   已反思过，跳过")
        return state

    filtered = state.get("filtered_papers", [])
    if not filtered:
        state["has_reflected"] = True
        return state

    # 只反思评分较低（3-4 分）的论文，5 分确信直接保留
    to_review = [p for p in filtered if p.relevance_score <= 4]
    keep_all = [p for p in filtered if p.relevance_score == 5]
    logger.info(f"   {len(keep_all)} 篇 5 分直接保留, {len(to_review)} 篇需要反思")

    if not to_review:
        state["has_reflected"] = True
        return state

    # 构造反思消息：每篇给标题 + 摘要尾部（结论部分）
    lines = []
    for p in to_review:
        abstract = p.abstract
        if len(abstract) > 1000:
            abstract_tail = abstract[:300] + " ... " + abstract[-700:]
        else:
            abstract_tail = abstract
        lines.append(
            f"---\nID: {p.arxiv_id}\n标题: {p.title}\n"
            f"初筛评分: {p.relevance_score}分\n初筛理由: {p.relevance_reason}\n"
            f"摘要: {abstract_tail}"
        )
    user_msg = "\n".join(lines)

    try:
        result = llm.chat_json(
            system_prompt=REFLECT_SYSTEM_PROMPT,
            user_message=user_msg,
            temperature=0.2,
            max_tokens=2048,
        )
        reviews = {r["arxiv_id"]: r for r in result.get("reviews", [])}
    except Exception as e:
        logger.error(f"   ❌ 反思调用失败，保留所有论文: {e}")
        state["has_reflected"] = True
        return state

    # 应用反思结果
    kept, dropped = [], []
    for p in to_review:
        review = reviews.get(p.arxiv_id)
        if review and review.get("verdict") == "drop":
            logger.info(f"   🗑️ 剔除: {p.title[:70]}... → {review.get('reason', '无理由')}")
            dropped.append(p)
        else:
            kept.append(p)

    new_filtered = keep_all + kept
    new_filtered.sort(key=lambda p: p.relevance_score, reverse=True)

    logger.info(f"   反思结果: 保留 {len(kept)} 篇, 剔除 {len(dropped)} 篇, 最终 {len(new_filtered)} 篇")

    state["filtered_papers"] = new_filtered
    state["has_reflected"] = True
    state["stats"] = {
        **state.get("stats", {}),
        "reflected_dropped": len(dropped),
        "filtered_count": len(new_filtered),
    }

    return state
