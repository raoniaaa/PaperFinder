"""Node 3: Agent B —— 学术中文梗概生成。"""

from src.state import AgentState
from src.models.paper import Paper, DigestedPaper
from src.models.llm import llm
from src.config import FILTER_TOP_K
from src.utils.logger import logger

DIGEST_SYSTEM_PROMPT = """你是「生成式引擎优化（Generative Engine Optimization, GEO）」领域的中文学术解读专家。
你的任务是将英文论文转化为结构化的中文梗概，要求准确、简洁、有洞察力。

请以 JSON 格式输出，包含以下字段：
{
  "chinese_title": "论文中文标题（意译，准确传达核心思想）",
  "one_line_contribution": "一句话说明这篇论文解决了什么核心痛点或提出了什么新发现（30字以内）",
  "methodology": "主要方法论、架构或技术路线（80字以内，说清用了什么方法）",
  "experiment_results": "关键实验设计与结果（80字以内，在什么设定下取得了什么效果）",
  "geo_insight": "对生成式引擎优化（GEO）领域的启发，对内容创作者、搜索引擎优化者或AI搜索研究者有何参考价值（60字以内）"
}

注意：
1. 翻译要自然流畅，避免生硬的直译
2. 专业术语保留英文缩写（如 RAG, LLM, SERP 等）
3. 不编造数据，忠实于原文
4. 如果论文与 GEO 领域直接相关，在 geo_insight 中明确指出其贡献；如果只是交叉领域，说明间接启发"""


def _digest_single_paper(paper: Paper) -> DigestedPaper | None:
    """对单篇论文生成中文梗概。"""
    user_msg = f"""请分析以下论文，生成中文梗概：

**标题**: {paper.title}
**作者**: {', '.join(paper.authors[:5])}{'...' if len(paper.authors) > 5 else ''}
**摘要**: {paper.abstract}"""

    try:
        result = llm.chat_json(
            system_prompt=DIGEST_SYSTEM_PROMPT,
            user_message=user_msg,
            temperature=0.3,
            max_tokens=2048,
        )

        return DigestedPaper(
            paper=paper,
            chinese_title=result.get("chinese_title", paper.title),
            one_line_contribution=result.get("one_line_contribution", ""),
            methodology=result.get("methodology", ""),
            experiment_results=result.get("experiment_results", ""),
            geo_insight=result.get("geo_insight", ""),
        )

    except Exception as e:
        logger.error(f"   ❌ 梗概生成失败 [{paper.arxiv_id}]: {e}")
        return None


def digest_papers(state: AgentState) -> AgentState:
    """Agent B: 对筛选后的论文逐一生成中文梗概。"""
    logger.info("=" * 60)
    logger.info("📝 Node 3: Agent B 开始生成中文梗概...")

    filtered = state.get("filtered_papers", [])
    if not filtered:
        logger.info("   无论文需要处理，跳过")
        state["digested_papers"] = []
        return state

    # 取 TOP_K 篇高分论文做深度梗概
    top_papers = filtered[:FILTER_TOP_K]
    logger.info(f"   将为 {len(top_papers)} 篇高优先级论文生成深度梗概")

    digested = []
    for i, paper in enumerate(top_papers):
        logger.info(f"   [{i+1}/{len(top_papers)}] 处理: {paper.title[:70]}...")
        digested_paper = _digest_single_paper(paper)
        if digested_paper:
            digested.append(digested_paper)
            logger.info(f"       ✅ 完成: {digested_paper.chinese_title}")

    logger.info(f"   ✅ 梗概生成完成: {len(digested)}/{len(top_papers)} 篇成功")

    state["digested_papers"] = digested
    state["stats"] = {
        **state.get("stats", {}),
        "digested_count": len(digested),
    }

    return state
