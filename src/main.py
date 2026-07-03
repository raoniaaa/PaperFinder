"""PaperForGeoAgent 入口 —— CLI + 定时调度。

用法:
    python -m src.main --run          # 手动触发一次完整流水线
    python -m src.main --schedule     # 启动定时调度器（每日定时执行）
    python -m src.main --search "关键词" # 搜索向量知识库
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# 确保 src 目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import SCHEDULE_TIME
from src.state import AgentState
from src.graph import graph
from src.storage.chroma import chroma_store
from src.utils.logger import logger


def run_pipeline() -> dict:
    """执行一次完整的论文抓取→筛选→梗概→存储→输出流水线。"""
    logger.info("🚀 启动 GEO 论文追踪流水线...")
    logger.info(f"   时间: {datetime.now().isoformat()}")

    initial_state: AgentState = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "raw_papers": [],
        "filtered_papers": [],
        "digested_papers": [],
        "output_message": "",
        "stats": {},
    }

    try:
        final_state = graph.invoke(initial_state)
        logger.info("✅ 流水线执行完成!")
        logger.info(f"   统计: {final_state.get('stats', {})}")
        return final_state
    except Exception as e:
        logger.error(f"❌ 流水线执行失败: {e}", exc_info=True)
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

    # 首次运行时可选择立即执行一次
    logger.info("💡 首次启动，立即执行一次测试...")
    scheduled_job()

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次
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
    parser.add_argument(
        "--run", action="store_true", help="手动触发一次完整流水线"
    )
    parser.add_argument(
        "--schedule", action="store_true", help="启动定时调度器"
    )
    parser.add_argument(
        "--search", type=str, default=None, help="搜索向量知识库"
    )
    parser.add_argument(
        "--top-k", type=int, default=5, help="搜索结果数量（默认5）"
    )

    args = parser.parse_args()

    if args.search:
        search_knowledge(args.search, top_k=args.top_k)
    elif args.schedule:
        run_schedule()
    elif args.run:
        run_pipeline()
    else:
        parser.print_help()
        print("\n示例:")
        print("  python -m src.main --run                # 手动运行一次")
        print("  python -m src.main --schedule           # 启动定时调度")
        print("  python -m src.main --search 'RAG优化'   # 搜索知识库")


if __name__ == "__main__":
    main()
