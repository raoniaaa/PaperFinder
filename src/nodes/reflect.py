"""Node 2.5: 反思节点 —— 在筛选后二次校验论文是否真正与 GEO 强相关。"""

from src.state import AgentState
from src.models.llm import llm
from src.utils.logger import logger
from src.config import GEO_HIGH_PRIORITY_KEYWORDS

REFLECT_SYSTEM_PROMPT = """你是「生成式引擎优化（GEO）」领域的审稿专家。你的任务是对已被初筛通过的论文进行二次反思，判断它们是否真正与 GEO 强相关。

GEO 核心定义：研究如何优化内容以在 AI 搜索引擎（ChatGPT、Perplexity、Google AI Overviews 等）中获得更好的曝光、引用和排名。

反思要点：
1. 这篇论文的核心贡献是否真的与 AI 搜索、生成式检索、内容可见性有关？
2. 是否只是蹭了 LLM/RAG 的热词，但实际做的是无关方向（如纯 CV、机器人、生物信息等）？
3. 摘要中是否有明确的实验结论或发现支持其与 GEO 的关联？
4. 是否存在"看起来相关但实际毫无 GEO 价值"的情况？

对每篇论文给出：
- verdict: "keep"（强相关，保留）或 "drop"（弱相关/误判，剔除）
- reason: 一句话说明理由（中文）

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
