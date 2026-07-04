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


def send_card_message(card: dict, receive_id: str | None = None, receive_id_type: str | None = None) -> bool:
    """发送飞书 Interactive Card 消息。

    Args:
        card: 飞书卡片 JSON（msg_type=interactive）
        receive_id: 目标 ID（open_id 或 chat_id），默认使用 .env 配置
        receive_id_type: open_id（私聊）或 chat_id（群聊），默认使用 .env 配置

    Returns:
        是否发送成功
    """
    target = receive_id or FEISHU_RECEIVE_ID
    id_type = receive_id_type or FEISHU_RECEIVE_ID_TYPE

    if not target:
        logger.error("❌ 飞书消息发送失败: 未配置 FEISHU_RECEIVE_ID")
        return False

    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logger.error("❌ 飞书消息发送失败: 未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
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
                "msg_type": "interactive",
                "content": json.dumps(card),
            },
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            logger.info(f"✅ 飞书日报已发送 (receive_id_type={id_type})")
            return True
        else:
            logger.error(f"❌ 飞书消息发送失败: {result}")
            return False
    except Exception as e:
        logger.error(f"❌ 飞书消息发送异常: {e}")
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
