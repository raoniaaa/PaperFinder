"""飞书消息事件长连接服务 (WebSocket) + 每日定时调度。"""

import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from src.config import FEISHU_APP_ID, FEISHU_APP_SECRET, SCHEDULE_TIME
from src.main import run_pipeline
from src.webhook_server import _handle_command, _send_text_reply
from src.utils.logger import logger


def _safe_get(obj, *attrs, default=""):
    """安全获取嵌套属性，任一环节为 None 则返回 default。"""
    for attr in attrs:
        if obj is None:
            return default
        obj = getattr(obj, attr, None)
    return obj if obj is not None else default


# 已处理消息 ID 缓存（防飞书重复推送）
_seen_messages: set[str] = set()


def _is_duplicate(message_id: str) -> bool:
    """检查消息是否已处理过（LRU 去重）。"""
    if message_id in _seen_messages:
        return True
    _seen_messages.add(message_id)
    # 保留最近 200 条，防止内存泄漏
    if len(_seen_messages) > 200:
        _seen_messages.clear()
    return False


def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    """接收并处理消息事件"""
    try:
        event = data.event
        msg = event.message

        # 只处理文本消息
        if msg.message_type != "text":
            return

        message_id = msg.message_id
        content_str = msg.content
        try:
            content = json.loads(content_str)
            text = content.get("text", "")
        except json.JSONDecodeError:
            text = content_str

        if not text.strip():
            return

        # 飞书 WebSocket 偶发重复推送同一条消息，去重
        if _is_duplicate(message_id):
            logger.info(f"🔌 [长连接] 跳过重复消息: {message_id}")
            return

        sender_id = _safe_get(event, "sender", "sender_id", "open_id")
        chat_id = _safe_get(msg, "chat_id")

        # 判断消息来源
        is_group = bool(chat_id and chat_id != sender_id)
        target_id = chat_id if is_group else sender_id
        target_type = "chat_id" if is_group else "open_id"

        logger.info(f"🔌 [长连接] 收到消息: '{text[:50]}' ({'群聊' if is_group else '私聊'})")

        # 处理命令（pipeline 内部会自己发进度+卡片）
        reply = _handle_command(text, target_id, target_type)

        # push 操作 pipeline 已自己发了卡片，不重复发文本；其他操作需要文本回复
        if not reply.startswith("✅") or "日报" not in reply:
            _send_text_reply(target_id, reply, message_id, target_type)

    except Exception:
        logger.error(f"❌ [长连接] 处理消息异常:\n{traceback.format_exc()}")


def main():
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logger.error("❌ 启动失败: 请先在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        return

    logger.info("🔌 正在与飞书服务器建立长连接 (WebSocket)...")

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
        .build()
    )

    ws_client = lark.ws.Client(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
        auto_reconnect=True,
    )

    # ─── 定时调度 ───
    import threading
    import os
    from src.config import FEISHU_RECEIVE_ID, FEISHU_RECEIVE_ID_TYPE

    def schedule_loop():
        """后台线程：每日定时推送"""
        hour, minute = SCHEDULE_TIME.split(":")
        target_hour, target_min = int(hour), int(minute)
        logger.info(f"⏰ 每日定时推送: {SCHEDULE_TIME} (北京时间)")
        last_run_date = None
        while True:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            if (now.hour == target_hour and now.minute >= target_min
                    and last_run_date != today_str):
                logger.info(f"⏰ 定时任务触发 @ {now}")
                try:
                    run_pipeline(feishu_chat_id=FEISHU_RECEIVE_ID,
                                 feishu_chat_type=FEISHU_RECEIVE_ID_TYPE)
                except Exception:
                    logger.error(f"定时任务失败", exc_info=True)
                last_run_date = today_str
            time.sleep(60)  # 每60秒检查一次

    threading.Thread(target=schedule_loop, daemon=True).start()

    logger.info("✅ 飞书长连接已就绪，正在监听事件...")
    ws_client.start()


if __name__ == "__main__":
    main()
