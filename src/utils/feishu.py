"""飞书 API 客户端 —— 获取 token + 发送卡片消息（支持私聊/群聊）。"""

import json
import time
import requests
from src.config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_RECEIVE_ID_TYPE, FEISHU_RECEIVE_ID
from src.utils.logger import logger

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
FEISHU_CHAT_LIST_URL = "https://open.feishu.cn/open-apis/im/v1/chats"
FEISHU_USER_LIST_URL = "https://open.feishu.cn/open-apis/contact/v3/users"

# 内存缓存
_cached_token: str = ""
_token_expires_at: float = 0


def _get_tenant_access_token() -> str:
    """获取 tenant_access_token（带缓存）。"""
    global _cached_token, _token_expires_at

    if _cached_token and time.time() < _token_expires_at - 60:
        return _cached_token

    resp = requests.post(
        FEISHU_TOKEN_URL,
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _cached_token = data["tenant_access_token"]
    _token_expires_at = time.time() + data.get("expire", 7200)
    return _cached_token


def send_card_message(card: dict, receive_id: str = "", receive_id_type: str = "") -> tuple[bool, str]:
    """发送飞书 Interactive Card 消息。

    Returns:
        (成功, message_id) — message_id 可用于后续 update_card_message
    """
    target = receive_id or FEISHU_RECEIVE_ID
    id_type = receive_id_type or FEISHU_RECEIVE_ID_TYPE

    if not target:
        logger.error("❌ 飞书卡片发送失败: 未配置 FEISHU_RECEIVE_ID，且未传入 receive_id")
        return False, ""

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logger.error("❌ 飞书消息发送失败: 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
        return False, ""

    try:
        token = _get_tenant_access_token()
        resp = requests.post(
            f"{FEISHU_MESSAGE_URL}?receive_id_type={id_type}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": target,
                "msg_type": "interactive",
                "content": json.dumps(card),
            },
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            message_id = result.get("data", {}).get("message_id", "")
            logger.info(f"✅ 飞书卡片已发送 (message_id={message_id})")
            return True, message_id
        else:
            logger.error(f"❌ 飞书卡片发送失败: {result}")
            return False, ""
    except Exception as e:
        logger.error(f"❌ 飞书卡片发送异常: {e}")
        return False, ""


def update_card_message(message_id: str, card: dict) -> bool:
    """更新已发送的飞书卡片（渐进式追加内容）。

    飞书文档: PATCH /im/v1/messages/:message_id
    """
    if not message_id or not FEISHU_APP_ID:
        return False

    try:
        token = _get_tenant_access_token()
        resp = requests.patch(
            f"{FEISHU_MESSAGE_URL}/{message_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "msg_type": "interactive",
                "content": json.dumps(card),
            },
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            logger.info(f"🔄 飞书卡片已更新 (message_id={message_id})")
            return True
        else:
            logger.warning(f"⚠️ 飞书卡片更新失败: {result}")
            return False
    except Exception as e:
        logger.warning(f"⚠️ 飞书卡片更新异常: {e}")
        return False


def list_chats(page_size: int = 20) -> list[dict]:
    """列出机器人所在的所有群聊，帮助用户找到 chat_id。"""
    if not FEISHU_APP_ID:
        logger.error("未配置 FEISHU_APP_ID")
        return []

    try:
        token = _get_tenant_access_token()
        resp = requests.get(
            f"{FEISHU_CHAT_LIST_URL}?page_size={page_size}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            chats = result.get("data", {}).get("items", [])
            return [{"chat_id": c["chat_id"], "name": c.get("name", "")} for c in chats]
        else:
            logger.error(f"获取群列表失败: {result}")
            return []
    except Exception as e:
        logger.error(f"获取群列表异常: {e}")
        return []


def send_text_message(text: str, receive_id: str = "", receive_id_type: str = "") -> bool:
    """发送纯文本消息到飞书（用于进度反馈）。

    Args:
        text: 要发送的文本内容
        receive_id: 目标 ID（open_id 或 chat_id），为空时使用 .env 配置
        receive_id_type: open_id（私聊）或 chat_id（群聊），为空时使用 .env 配置

    Returns:
        是否发送成功
    """
    target = receive_id or FEISHU_RECEIVE_ID
    id_type = receive_id_type or FEISHU_RECEIVE_ID_TYPE

    if not target:
        return False

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        return False

    try:
        token = _get_tenant_access_token()
        resp = requests.post(
            f"{FEISHU_MESSAGE_URL}?receive_id_type={id_type}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": target,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            logger.info(f"📤 进度消息已发送: {text[:50]}...")
            return True
        else:
            logger.warning(f"⚠️ 进度消息发送失败: {result}")
            return False
    except Exception as e:
        logger.warning(f"⚠️ 进度消息发送异常: {e}")
        return False


def list_users(page_size: int = 50) -> list[dict]:
    """列出企业内用户，帮助找到 open_id 用于私聊。"""
    if not FEISHU_APP_ID:
        logger.error("未配置 FEISHU_APP_ID")
        return []

    try:
        token = _get_tenant_access_token()
        resp = requests.get(
            f"{FEISHU_USER_LIST_URL}?page_size={page_size}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            users = result.get("data", {}).get("items", [])
            return [
                {"name": u.get("name", ""), "open_id": u.get("open_id", ""), "email": u.get("email", "")}
                for u in users
            ]
        else:
            logger.error(f"获取用户列表失败: {result}")
            return []
    except Exception as e:
        logger.error(f"获取用户列表异常: {e}")
        return []
