"""Node 5: 终端输出 + 飞书卡片数据结构预留。"""

from src.state import AgentState
from src.models.paper import DigestedPaper
from src.config import FILTER_TOP_K
from src.utils.logger import logger


def _render_daily_report(state: AgentState) -> str:
    """渲染每日论文日报（Markdown 格式）。"""
    date = state.get("date", "未知日期")
    digested = state.get("digested_papers", [])
    filtered = state.get("filtered_papers", [])
    stats = state.get("stats", {})

    lines = [
        "╔══════════════════════════════════════════════════════════╗",
        "║       📊 GEO 论文日报 —— Generative Engine Optimization   ║",
        f"║                    {date}                              ║",
        "╚══════════════════════════════════════════════════════════╝",
        "",
        f"📬 今日抓取: {stats.get('total_fetched', 0)} 篇",
        f"🔍 筛选通过: {stats.get('filtered_count', 0)} 篇",
        f"📝 深度梗概: {len(digested)} 篇",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  📌 精选论文",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    # 深度梗概部分
    if digested:
        for i, dp in enumerate(digested):
            paper = dp.paper
            lines.extend([
                f"  【{i+1}】 {dp.chinese_title}",
                f"        📄 原文: {paper.title}",
                f"        👤 作者: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}",
                f"        📅 {paper.published_date}  |  📂 {paper.primary_category}",
                "",
                f"        💡 {dp.one_line_contribution}",
                f"        🛠️ {dp.methodology}",
                f"        📈 {dp.experiment_results}",
                f"        🔗 {dp.geo_insight}",
                "",
                f"        🔗 arXiv: {paper.pdf_url}",
                "",
                "  ─────────────────────────────────────────",
                "",
            ])

    # 其他通过筛选但未做深度梗概的论文列表
    remaining = filtered[len(digested):] if len(filtered) > len(digested) else []
    if remaining:
        lines.append("  📋 其他值得关注的论文:")
        lines.append("")
        for paper in remaining:
            lines.append(f"    ⭐ [{paper.relevance_score}分] {paper.title}")
            lines.append(f"       理由: {paper.relevance_reason}")
            lines.append(f"       链接: {paper.pdf_url}")
            lines.append("")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  📊 Chroma 知识库: {stats.get('chroma_total', 0)} 篇论文已索引",
        "  🗣️  后续可 @机器人 进行语义搜索和对话问答",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])

    return "\n".join(lines)


def _build_feishu_card_data(state: AgentState) -> dict:
    """构建飞书 Interactive Card 数据结构（预留）。"""
    date = state.get("date", "")
    digested = state.get("digested_papers", [])

    # 飞书卡片消息结构
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": f"📊 GEO 论文日报 | {date}"},
        },
        "elements": [],
    }

    for dp in digested:
        p = dp.paper
        card["elements"].append({
            "tag": "div",
            "fields": [
                {"is_short": False, "text": {"tag": "lark_md", "content": f"**📄 {dp.chinese_title}**"}},
                {"is_short": False, "text": {"tag": "lark_md", "content": f"*原文: {p.title}*"}},
                {"is_short": False, "text": {"tag": "lark_md", "content": f"💡 {dp.one_line_contribution}"}},
                {"is_short": False, "text": {"tag": "lark_md", "content": f"🛠️ {dp.methodology}"}},
                {"is_short": False, "text": {"tag": "lark_md", "content": f"📈 {dp.experiment_results}"}},
                {"is_short": False, "text": {"tag": "lark_md", "content": f"🔗 {dp.geo_insight}"}},
            ],
        })
        card["elements"].append({"tag": "hr"})

    card["elements"].append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": f"共 {len(digested)} 篇精选 | 数据来源: arXiv"}],
    })

    return card


def output_result(state: AgentState) -> AgentState:
    """输出最终日报到终端，并预留飞书卡片数据。"""
    logger.info("=" * 60)
    logger.info("📤 Node 5: 生成输出...")

    # 生成日报文本
    report = _render_daily_report(state)
    state["output_message"] = report

    # 打印到终端
    print(report)
    logger.info(f"   ✅ 日报生成完成，共 {len(state.get('digested_papers', []))} 篇深度梗概")

    # 预留飞书卡片数据
    feishu_card = _build_feishu_card_data(state)
    logger.info(f"   📋 飞书卡片数据已准备（{len(feishu_card.get('elements', []))} 个元素）")

    return state
