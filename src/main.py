"""PaperForGeoAgent 入口 —— CLI + 定时调度。

用法:
    python -m src.main --run                     # 手动触发一次完整流水线（自动找最近有论文的日期）
    python -m src.main --run --date 2026-07-03   # 指定日期抓取
    python -m src.main --schedule                 # 启动定时调度器（每日定时执行）
    python -m src.main --search "关键词"          # 搜索向量知识库
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 确保 src 目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import SCHEDULE_TIME
from src.state import AgentState
from src.graph import build_graph
from src.nodes.fetch import _build_query
from src.storage.chroma import chroma_store
from src.storage.sqlite import paper_store
from src.utils.logger import logger
from src.utils.feishu import list_chats, list_users, send_card_message, send_text_message
from src.nodes.output import _build_feishu_card_data, _render_daily_report

# 回退查找配置
MAX_LOOKBACK_DAYS = 14       # 最多往回找多少天
QUICK_CHECK_TIMEOUT = 5      # 回退时每天查询超时（秒），不重试


def _find_latest_day_with_papers() -> str:
    """快速回退查找最近一个有论文的日期。

    用 arxiv 客户端但禁内置重试 + 短超时，单日最多 QUICK_CHECK_TIMEOUT 秒。
    最多回退 MAX_LOOKBACK_DAYS 天，找不到就用昨天。
    """
    import arxiv

    today = datetime.now()
    # 跳过周末（arXiv 通常不在周末发布）
    client = arxiv.Client(page_size=5, delay_seconds=0, num_retries=0)

    for offset in range(1, MAX_LOOKBACK_DAYS + 1):
        candidate = today - timedelta(days=offset)
        candidate_str = candidate.strftime("%Y-%m-%d")

        # 跳过周末
        weekday = candidate.weekday()  # 0=Mon ... 6=Sun
        if weekday >= 5:
            logger.info(f"🔍 跳过周末 {candidate_str} ({['一','二','三','四','五','六','日'][weekday]})")
            continue

        logger.info(f"🔍 快速探测: {candidate_str} ...")
        query = _build_query(candidate_str)
        try:
            # 最多只查 3 篇，判断有没有就行
            search = arxiv.Search(query=query, max_results=3, sort_by=arxiv.SortCriterion.SubmittedDate)
            results = list(client.results(search))
            if results:
                logger.info(f"   ✅ 找到论文，日期: {candidate_str}")
                return candidate_str
            else:
                logger.info(f"   无论文")
        except Exception:
            logger.info(f"   查询失败，快速跳过")
            continue

    fallback = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    logger.warning(f"⚠️ 回退 {MAX_LOOKBACK_DAYS} 天均无结果，使用 {fallback}")
    return fallback


def run_pipeline(
    target_date: str | None = None,
    feishu_chat_id: str = "",
    feishu_chat_type: str = "",
) -> dict:
    """执行一次完整的论文抓取→筛选→梗概→存储→输出流水线。

    Args:
        target_date: 目标日期 YYYY-MM-DD，为 None 时自动找最近有论文的一天。
        feishu_chat_id: 飞书用户 open_id 或群 chat_id，用于进度推送。
        feishu_chat_type: "open_id"（私聊）或 "chat_id"（群聊）。
    """
    if target_date is None:
        target_date = _find_latest_day_with_papers()

    logger.info("🚀 启动 GEO 论文追踪流水线...")
    logger.info(f"   目标日期: {target_date}")
    logger.info(f"   当前时间: {datetime.now().isoformat()}")

    # ── 快捷路径：如果该日期已有缓存数据，直接复用 ──
    cached = paper_store.get_by_date(target_date)
    if cached:
        logger.info(f"⏭️ {target_date} 已有 {len(cached)} 篇缓存数据，跳过抓取和筛选")
        state: AgentState = {
            "date": target_date,
            "raw_papers": [],
            "filtered_papers": [d.paper for d in cached],
            "digested_papers": cached,
            "output_message": "",
            "stats": {
                "total_fetched": len(cached),
                "filtered_count": len(cached),
                "digested_count": len(cached),
                "chroma_total": chroma_store.count(),
                "from_cache": True,
            },
            "has_reflected": True,
            "feishu_chat_id": feishu_chat_id,
            "feishu_chat_type": feishu_chat_type,
        }
        report = _render_daily_report(state)
        try:
            print(report)
        except UnicodeEncodeError:
            print(report.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
        feishu_card = _build_feishu_card_data(state)
        send_card_message(feishu_card, receive_id=feishu_chat_id, receive_id_type=feishu_chat_type)
        return state

    initial_state: AgentState = {
        "date": target_date,
        "raw_papers": [],
        "filtered_papers": [],
        "digested_papers": [],
        "output_message": "",
        "stats": {},
        "has_reflected": False,
        "feishu_chat_id": feishu_chat_id,
        "feishu_chat_type": feishu_chat_type,
    }

    try:
        final_state = build_graph().invoke(initial_state)
        logger.info("✅ 流水线执行完成!")
        logger.info(f"   统计: {final_state.get('stats', {})}")
        return final_state
    except Exception as e:
        logger.error(f"❌ 流水线执行失败: {e}", exc_info=True)
        if feishu_chat_id:
            send_text_message(f"❌ 流水线执行失败: {e}", receive_id=feishu_chat_id, receive_id_type=feishu_chat_type)
        raise


def run_schedule():
    """启动定时调度器，每日在指定时间执行。"""
    import schedule

    hour, minute = SCHEDULE_TIME.split(":")
    schedule_time = f"{hour}:{minute}"
    logger.info(f"⏰ 定时调度已启动，将在每日 {schedule_time} (北京时间) 执行")
    logger.info("   按 Ctrl+C 退出...")

    def scheduled_job():
        logger.info(f"⏰ 定时任务触发 @ {datetime.now()}")
        try:
            run_pipeline()
        except Exception as e:
            logger.error(f"定时任务执行失败: {e}")

    schedule.every().day.at(schedule_time).do(scheduled_job)

    first_run = os.getenv("SCHEDULE_RUN_ON_START", "false").lower() == "true"
    if first_run:
        logger.info("💡 首次启动，立即执行一次测试...")
        scheduled_job()

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("👋 调度器已停止")


def search_knowledge(query: str, top_k: int = 5):
    """搜索向量知识库。"""
    logger.info(f"🔍 搜索知识库: '{query}'")
    results = chroma_store.search(query, top_k=top_k)

    if not results:
        print("\n未找到相关论文。")
        return

    print(f"\n🔍 找到 {len(results)} 篇相关论文:\n")
    for i, r in enumerate(results):
        print(f"  【{i+1}】 {r['chinese_title']}")
        print(f"        📄 {r['title']}")
        print(f"        📅 {r['published_date']}  |  ⭐ {r['relevance_score']}分")
        print(f"        📝 {r['snippet']}...")
        print(f"        🔗 {r['pdf_url']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="GEO 论文追踪智能体 (Generative Engine Optimization)",
    )
    parser.add_argument("--run", action="store_true", help="手动触发一次完整流水线")
    parser.add_argument("--date", type=str, default=None, metavar="YYYY-MM-DD",
                        help="指定抓取日期（默认自动找最近有论文的一天）")
    parser.add_argument("--schedule", action="store_true", help="启动定时调度器")
    parser.add_argument("--search", type=str, default=None, help="搜索向量知识库")
    parser.add_argument("--top-k", type=int, default=5, help="搜索结果数量（默认5）")
    parser.add_argument("--list-chats", action="store_true", help="查看飞书可用群聊")
    parser.add_argument("--list-users", action="store_true", help="查看飞书用户（获取 open_id 用于私聊）")

    args = parser.parse_args()

    if args.search:
        search_knowledge(args.search, top_k=args.top_k)
    elif args.schedule:
        run_schedule()
    elif args.run:
        run_pipeline(target_date=args.date)
    elif args.list_chats:
        print("📋 正在获取飞书群列表...\n")
        chats = list_chats()
        if chats:
            for c in chats:
                print(f"  {c['name']:20s}  →  {c['chat_id']}")
            print(f"\n共 {len(chats)} 个群。将你需要的 chat_id 填入 .env 的 FEISHU_RECEIVE_ID，\n"
                  "并设置 FEISHU_RECEIVE_ID_TYPE=chat_id。")
        else:
            print("未找到群聊，请确保:\n"
                  "  1. 将机器人添加到需要发送消息的群\n"
                  "  2. 已启用 im:chat 相关权限\n"
                  "  3. 已发布应用版本")
    elif args.list_users:
        print("📋 正在获取用户列表...\n")
        users = list_users()
        if users:
            for u in users:
                print(f"  {u['name']:15s}  {u['email']:30s}  open_id={u['open_id']}")
            print(f"\n共 {len(users)} 个用户。将你的 open_id 填入 .env 的 FEISHU_RECEIVE_ID，\n"
                  "并设置 FEISHU_RECEIVE_ID_TYPE=open_id。")
        else:
            print("未找到用户，请确保:\n"
                  "  1. 已启用 contact:user:readonly 权限\n"
                  "  2. 已发布应用版本")
    else:
        parser.print_help()
        print("\n示例:")
        print("  python -m src.main --run                # 自动找最近有论文的日期")
        print("  python -m src.main --run --date 2026-07-03  # 指定日期")
        print("  python -m src.main --schedule           # 启动定时调度")
        print("  python -m src.main --search 'RAG优化'   # 搜索知识库")
        print("  python -m src.main --list-chats         # 查看飞书可用群聊")


if __name__ == "__main__":
    main()
