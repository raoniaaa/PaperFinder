"""Node 2: Agent A —— 论文相关性筛选（带断点恢复 + 卡片渐进）。"""

import copy
from src.state import AgentState
from src.models.paper import Paper
from src.models.llm import llm
from src.storage.sqlite import paper_store
from src.config import (
    FILTER_BATCH_SIZE,
    FILTER_MIN_SCORE,
    GEO_HIGH_PRIORITY_KEYWORDS,
    GEO_MEDIUM_PRIORITY_KEYWORDS,
    GEO_NEGATIVE_KEYWORDS,
)
from src.utils.logger import logger
from src.utils.feishu import send_card_message, update_card_message

FILTER_SYSTEM_PROMPT = """你是「生成式引擎优化（Generative Engine Optimization, GEO）」领域的资深研究专家。
你的任务是评估一组论文摘要，判断它们是否**直接研究 GEO 本身**，而非从其他领域间接关联 GEO。

GEO 严格定义：研究如何优化内容以在 AI 搜索引擎（ChatGPT、Perplexity、Google AI Overviews、Bing Copilot 等）中获得更好的可见性、引用和排名。核心问题是"内容如何在 AI 答案中被引用/推荐"。

评分标准：

- 5分：论文直接研究以下问题之一：
  * AI 搜索引擎中的内容排名/可见性/优化策略
  * Generative Engine Optimization / Answer Engine Optimization
  * AI 搜索引擎对内容生态的影响（网站流量、点击行为、引用模式）
  * 如何让内容被 LLM 引用的方法/实验

- 4分：论文研究以下问题，且摘要中有明确实验/结论而非纯框架：
  * AI 搜索结果的引用/归因机制（citation/attribution in AI search）
  * LLM 回答中的信息来源选择与排序
  * AI Overviews / AI-generated answers 的内容呈现与 bias

- 3分：论文间接相关，但核心贡献不在 GEO：
  * RAG 检索质量优化（不涉及 AI 搜索场景而是知识库问答）
  * 幻觉缓解（不涉及内容发布者视角）
  * 通用 IR + LLM 交叉（不涉及搜索引擎场景）

- 2分：论文与 GEO 几乎无关：
  * 纯 RAG 架构改进、向量检索优化、非搜索场景的 LLM 应用
  * 涉及 LLM 但不讨论搜索/内容可见性/引用

- 1分：完全无关：CV、机器人、生物信息、通用 NLP 等

⚠️ ★ 核心判断原则 ★：
"能从 AI 搜索中获得什么启发" ≠ "论文研究了 AI 搜索"
一篇 RAG 问答系统的论文即使"对 GEO 有启发"，如果它本身没有研究 AI 搜索引擎中的内容优化，也只给 2-3 分。
只有论文核心问题直接关于 AI 搜索中内容的可见性/排名/引用时，才给 4-5 分。

请为每篇论文给出：
1. relevance_score: 1-5 的整数评分
2. relevance_reason: 一句话说明理由（中文，明确指出论文的**核心研究问题**是什么，以及是否直接研究 AI 搜索/内容可见性）

严格按照以下 JSON 格式输出：
{{
  "papers": [
    {{"arxiv_id": "论文ID", "relevance_score": 4, "relevance_reason": "理由"}},
    ...
  ]
}}"""


def _build_filter_user_message(abstracts_batch):
    lines = []
    for arxiv_id, title, abstract in abstracts_batch:
        if len(abstract) > 1500:
            abstract_short = abstract[:400] + " ... " + abstract[-1100:]
        else:
            abstract_short = abstract
        lines.append(f"---\nID: {arxiv_id}\n标题: {title}\n摘要: {abstract_short}")
    return "\n".join(lines)


def _hard_filter_negative(text: str) -> bool:
    for kw in GEO_NEGATIVE_KEYWORDS:
        if kw.lower() in text.lower():
            return True
    return False


def _hard_filter_positive(text: str) -> int:
    return sum(1 for kw in GEO_HIGH_PRIORITY_KEYWORDS if kw.lower() in text.lower())


def _paper_to_dict(p: Paper) -> dict:
    return {
        "arxiv_id": p.arxiv_id, "title": p.title, "authors": p.authors,
        "abstract": p.abstract, "published_date": p.published_date,
        "pdf_url": p.pdf_url, "primary_category": p.primary_category,
        "relevance_score": p.relevance_score, "relevance_reason": p.relevance_reason,
    }


def _dict_to_paper(d: dict) -> Paper:
    p = Paper(
        arxiv_id=d["arxiv_id"], title=d["title"], authors=d["authors"],
        abstract=d["abstract"], published_date=d["published_date"],
        pdf_url=d["pdf_url"], primary_category=d["primary_category"],
    )
    p.relevance_score = d.get("relevance_score", 0)
    p.relevance_reason = d.get("relevance_reason", "")
    return p


def _build_progress_card(date: str, batch_num: int, total_batches: int, passed: int,
                         progress_lines: list[str]) -> dict:
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content":
         f"**📊 GEO 论文筛选中 | {date}**\n\n进度：批次 {batch_num}/{total_batches} | 已通过 {passed} 篇\n"}},
        {"tag": "hr"},
    ]
    for line in progress_lines[-20:]:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": line}})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": f"🔍 GEO 论文筛选中 | {date}"}},
        "elements": elements,
    }


def filter_papers(state: AgentState) -> AgentState:
    logger.info("=" * 60)
    logger.info("🔍 Node 2: Agent A 开始筛选论文...")

    raw_papers = state.get("raw_papers", [])
    target = state.get("feishu_chat_id", "")
    target_type = state.get("feishu_chat_type", "open_id")
    date = state.get("date", "")

    if not raw_papers:
        logger.info("   无论文需要筛选，跳过")
        state["filtered_papers"] = []
        state["stats"] = {**state.get("stats", {}), "filtered_count": 0}
        return state

    total = len(raw_papers)
    total_batches = (total + FILTER_BATCH_SIZE - 1) // FILTER_BATCH_SIZE
    prompt = FILTER_SYSTEM_PROMPT.format(
        high_kw=", ".join(GEO_HIGH_PRIORITY_KEYWORDS),
        med_kw=", ".join(GEO_MEDIUM_PRIORITY_KEYWORDS),
        neg_kw=", ".join(GEO_NEGATIVE_KEYWORDS),
    )

    # ─── 断点恢复 ───
    cp = paper_store.load_checkpoint(date)
    scored_papers: list[Paper] = []
    start_batch = 0
    card_msg_id = state.get("feishu_card_message_id", "")
    if cp and cp.get("scored_data"):
        logger.info(f"   🔄 从断点恢复: 已完成 {cp['batch_index']}/{total_batches} 批")
        scored_papers = [_dict_to_paper(d) for d in cp["scored_data"]]
        start_batch = cp["batch_index"]
        if cp.get("card_message_id") and not card_msg_id:
            card_msg_id = cp["card_message_id"]

    # ─── 初始化卡片 ───
    progress_lines = [f"📡 抓取完成: {total} 篇论文"]
    if start_batch > 0:
        progress_lines.append(f"🔄 从断点恢复，已完成 {start_batch}/{total_batches} 批")

    if not card_msg_id and target:
        ok, card_msg_id = send_card_message(
            _build_progress_card(date, start_batch, total_batches,
                                 _count_passed(scored_papers), progress_lines),
            receive_id=target, receive_id_type=target_type)
        if ok:
            state["feishu_card_message_id"] = card_msg_id
            paper_store.save_checkpoint(date, "filter", start_batch,
                                        scored_data=[_paper_to_dict(p) for p in scored_papers],
                                        card_message_id=card_msg_id)
            progress_lines.append("🔍 开始 LLM 筛选...")

    # ─── 筛选循环 ───
    for i in range(start_batch * FILTER_BATCH_SIZE, total, FILTER_BATCH_SIZE):
        batch = raw_papers[i : i + FILTER_BATCH_SIZE]
        batch_num = i // FILTER_BATCH_SIZE + 1

        filtered_batch = []
        for p in batch:
            if not _hard_filter_negative(f"{p.title} {p.abstract}"):
                filtered_batch.append(p)

        if not filtered_batch:
            progress_lines.append(f"批次 {batch_num}/{total_batches}: 全部硬过滤，跳过")
            _save_and_update(date, "filter", batch_num, card_msg_id, scored_papers,
                             progress_lines, total_batches, _count_passed(scored_papers))
            continue

        batch_data = [(p.arxiv_id, p.title, p.abstract) for p in filtered_batch]
        logger.info(f"   处理批次 {batch_num}/{total_batches}, 共 {len(filtered_batch)} 篇...")

        batch_passed = 0
        try:
            result = llm.chat_json(system_prompt=prompt,
                                   user_message=_build_filter_user_message(batch_data),
                                   temperature=0.2)
            scores = {item["arxiv_id"]: (int(item["relevance_score"]), item["relevance_reason"])
                      for item in result.get("papers", [])}

            for paper in filtered_batch:
                if paper.arxiv_id in scores:
                    s, reason = scores[paper.arxiv_id]
                    if s >= 4 and _hard_filter_positive(f"{paper.title} {paper.abstract}") == 0:
                        s, reason = 3, f"[降级] {reason}（未命中高优先级关键词）"
                    paper.relevance_score, paper.relevance_reason = s, reason
                    scored_papers.append(paper)
                    if s >= FILTER_MIN_SCORE:
                        batch_passed += 1
            progress_lines.append(f"✅ 批次 {batch_num}/{total_batches}: {len(filtered_batch)} 篇 → 通过 {batch_passed} 篇")
        except Exception as e:
            logger.error(f"   ❌ 批次 {batch_num} 失败: {e}")
            for paper in filtered_batch:
                paper.relevance_score, paper.relevance_reason = 1, "LLM 异常，默认低分"
                scored_papers.append(paper)
            progress_lines.append(f"❌ 批次 {batch_num}/{total_batches}: LLM 失败")

        _save_and_update(date, "filter", batch_num, card_msg_id, scored_papers,
                         progress_lines, total_batches, _count_passed(scored_papers))

    filtered = [p for p in scored_papers if p.relevance_score >= FILTER_MIN_SCORE]
    filtered.sort(key=lambda p: p.relevance_score, reverse=True)
    logger.info(f"   ✅ 筛选完成: {len(filtered)}/{total} 篇通过")
    state["filtered_papers"] = filtered
    state["stats"] = {**state.get("stats", {}), "filtered_count": len(filtered), "total_fetched": total}
    return state


def _count_passed(papers):
    return len([p for p in papers if p.relevance_score >= FILTER_MIN_SCORE])


def _save_and_update(date, phase, batch_index, card_msg_id, scored_papers, lines, total, passed):
    paper_store.save_checkpoint(
        date, phase, batch_index,
        scored_data=[_paper_to_dict(p) for p in scored_papers],
        card_message_id=card_msg_id)
    if card_msg_id:
        update_card_message(card_msg_id, _build_progress_card(date, batch_index, total, passed, lines))
