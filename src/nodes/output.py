"""Node 5: 终端输出 + 飞书卡片推送。"""

import json
from src.state import AgentState
from src.models.paper import DigestedPaper
from src.config import FILTER_TOP_K
from src.utils.logger import logger
from src.utils.feishu import send_card_message, send_text_message


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
                {"is_short": False, "text": {"tag": "lark_md", "content": f"[📄 查看论文]({p.pdf_url})"}},
            ],
        })
        card["elements"].append({"tag": "hr"})

    card["elements"].append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": f"共 {len(digested)} 篇精选 | 数据来源: arXiv"}],
    })

    return card


def output_result(state: AgentState) -> AgentState:
    """输出最终日报：有论文发卡片，无论文发文本说明。"""
    logger.info("=" * 60)
    logger.info("📤 Node 5: 生成输出...")

    feishu_target = state.get("feishu_chat_id", "")
    feishu_type = state.get("feishu_chat_type", "")

    # 生成日报文本
    report = _render_daily_report(state)
    state["output_message"] = report

    try:
        print(report)
    except UnicodeEncodeError:
        print(report.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

    digested = state.get("digested_papers", [])
    logger.info(f"   ✅ 日报生成完成，共 {len(digested)} 篇深度梗概")

    if digested:
        # 有论文 → 先尝试更新进度卡片为日报，失败则发新卡片
        card_msg_id = state.get("feishu_card_message_id", "")
        feishu_card = _build_feishu_card_data(state)
        if card_msg_id:
            # 把进度卡片原地变身为日报卡片
            updated = update_card_message(card_msg_id, feishu_card)
            if updated:
                logger.info(f"   ✅ 进度卡片已更新为日报 (message_id={card_msg_id})")
                return state
        ok, _ = send_card_message(feishu_card, receive_id=feishu_target, receive_id_type=feishu_type)
        if ok:
            logger.info(f"   ✅ 飞书日报卡片已发送到 {feishu_type}={feishu_target}")
        else:
            logger.warning(f"   ⚠️ 飞书卡片发送失败")
    else:
        # 无论文 → 发送一条文本摘要（不发空卡片）
        date = state.get("date", "")
        stats = state.get("stats", {})
        total = stats.get("total_fetched", 0)
        if total:
            msg = f"📊 GEO 论文日报 | {date}\n\n📬 抓取 {total} 篇，但经筛选无与 GEO 强相关的论文。\n可尝试换日期或搜索知识库 🔍"
        else:
            msg = f"📊 GEO 论文日报 | {date}\n\n⚠️ 该日期 arXiv 无新论文或 API 暂时不可用（arXiv 周末/节假日通常不发布）。\n可尝试换日期或搜索知识库 🔍"
        if feishu_target:
            send_text_message(msg, receive_id=feishu_target, receive_id_type=feishu_type)
            logger.info(f"   ✅ 无结果通知已发送")

    return state
