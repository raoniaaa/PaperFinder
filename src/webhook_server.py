"""飞书消息事件回调 Webhook —— Flask 服务，接收用户消息并触发对应操作。"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 确保 src 目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, request, jsonify
from src.main import run_pipeline, search_knowledge
from src.models.llm import llm
from src.utils.logger import logger

app = Flask(__name__)


# ─── LLM 意图识别 ───

INTENT_SYSTEM_PROMPT = """你是一个意图识别助手。根据用户消息判断意图，返回 JSON。

意图类型：
- "push": 用户想要推送/获取论文日报
- "search": 用户想要搜索/查找论文
- "help": 用户询问功能或请求帮助
- "unknown": 无法识别

时间偏移（仅 push 意图需要）：
- "today": 今日/今天
- "yesterday": 昨天/昨日
- "latest": 最近/最新（未明确指定日期时）
- "none": 非推送意图

分析规则：
- "看看今天有什么"、"推送今天"、"今日论文"、"今天日报"、"今天有什么论文" → push + today
- "昨天"、"昨天的"、"推送昨天" → push + yesterday
- "推送"、"推荐论文"、"论文日报"、"来一份"、"最近有什么"、"有什么新论文" → push + latest
- "搜索xxx"、"找一下"、"有没有xxx"、"查找" → search
- "你能做什么"、"怎么用"、"功能"、"帮助" → help
- 闲聊或其他 → unknown

返回格式：
{"intent": "push|search|help|unknown", "time_offset": "today|yesterday|latest|none", "search_query": "关键词或空字符串"}"""


def _classify_intent(text: str) -> dict:
    """用 LLM 识别用户意图。"""
    try:
        result = llm.chat_json(
            system_prompt=INTENT_SYSTEM_PROMPT,
            user_message=text,
            temperature=0.1,
            max_tokens=128,
        )
        logger.info(f"🧠 意图识别: '{text}' → {result}")
        return result
    except Exception as e:
        logger.error(f"意图识别失败，回退到关键词匹配: {e}")
        return _classify_fallback(text)


def _classify_fallback(text: str) -> dict:
    """关键词回退（LLM 调用失败时使用）。"""
    text_lower = text.strip().lower()
    if any(kw in text for kw in ["搜索", "搜索", "查找", "找", "有没有"]):
        query = re.sub(r"^(搜索|查找|找一下|有没有)\s*", "", text)
        return {"intent": "search", "time_offset": "none", "search_query": query}
    if any(kw in text for kw in ["帮助", "功能", "能做什么", "怎么用"]):
        return {"intent": "help", "time_offset": "none", "search_query": ""}
    if any(kw in text for kw in ["推送", "论文", "日报", "看看", "有什么", "来一份"]):
        if any(kw in text for kw in ["昨天", "昨天", "昨日"]):
            return {"intent": "push", "time_offset": "yesterday", "search_query": ""}
        if any(kw in text for kw in ["今天", "今天", "今日"]):
            return {"intent": "push", "time_offset": "today", "search_query": ""}
        return {"intent": "push", "time_offset": "latest", "search_query": ""}
    return {"intent": "unknown", "time_offset": "none", "search_query": ""}


# ─── 命令处理 ───

def _handle_command(text: str, sender_open_id: str) -> str:
    """解析用户消息，执行对应的操作，返回回复文本。"""
    intent = _classify_intent(text)

    # 推送论文
    if intent["intent"] == "push":
        offset = intent.get("time_offset", "latest")
        if offset == "today":
            target = datetime.now().strftime("%Y-%m-%d")
            label = f"今日论文日报（{target}）"
        elif offset == "yesterday":
            target = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            label = f"昨天论文日报（{target}）"
        else:
            target = None
            label = "最近论文日报"

        logger.info(f"📨 推送请求: {label}")
        try:
            run_pipeline(target_date=target)
            return f"✅ {label}已推送，请查收"
        except Exception as e:
            logger.error(f"推送失败: {e}")
            return f"❌ 推送失败: {e}"

    # 搜索
    if intent["intent"] == "search":
        query = intent.get("search_query", "").strip()
        if not query:
            return "请问你想搜索什么关键词？例如：搜索 RAG优化"
        logger.info(f"📨 搜索请求: {query}")
        try:
            results = search_knowledge(query, top_k=5)
            if not results:
                return f"🔍 未找到与「{query}」相关的论文。"
            lines = [f"🔍 **「{query}」相关论文** Top {len(results)}:\n"]
            for i, r in enumerate(results):
                lines.append(
                    f"**【{i+1}】** {r['chinese_title']}\n"
                    f"📄 {r['title']}\n"
                    f"📅 {r['published_date']} | ⭐ {r['relevance_score']}分\n"
                    f"🔗 {r['pdf_url']}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return f"❌ 搜索失败: {e}"

    # 帮助
    if intent["intent"] == "help":
        return (
            "📋 **我是 GEO 论文助手，支持以下操作：**\n"
            "📬 推送今日论文 / 推送昨天论文 / 推送最近论文\n"
            "🔍 搜索 <关键词> — 从知识库查找论文\n"
            "💬 直接跟我聊天，我会自动理解你的意图\n\n"
            "你也可以这样说：\n"
            "• 「今天有什么论文」\n"
            "• 「找一下 RAG 相关的」\n"
            "• 「最近有什么新东西」"
        )

    # 未知
    return (
        f"🤔 不太确定你的意思～\n\n"
        "你可以这样跟我说：\n"
        "• 推送今日论文\n"
        "• 搜索 RAG优化\n"
        "• 帮助"
    )


# ─── 飞书回调路由 ───

@app.route("/feishu/webhook", methods=["POST"])
def feishu_webhook():
    """飞书事件回调入口。"""
    body = request.get_json(force=True, silent=True)
    if not body:
        return jsonify({"error": "invalid json"}), 400

    # 1. URL 验证（首次配置时飞书会发 challenge）
    if body.get("type") == "url_verification":
        token = body.get("token", "")
        challenge = body.get("challenge", "")
        logger.info(f"🔑 收到 URL 验证请求, token={token}")
        return jsonify({"challenge": challenge})

    # 2. 事件回调
    if body.get("type") == "event_callback":
        event = body.get("event", {})
        event_type = event.get("type", "")
        msg_type = event.get("msg_type", "")

        # 只处理文本消息
        if event_type == "im.message.receive_v1" and msg_type == "text":
            message_id = event.get("message_id", "")
            # 提取纯文本内容
            content_str = event.get("content", "{}")
            try:
                content = json.loads(content_str)
                text = content.get("text", "")
            except json.JSONDecodeError:
                text = content_str

            sender_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")

            logger.info(f"📨 收到消息: '{text}' from {sender_id}")

            # 处理命令并回复（这里简化：直接通过飞书消息 API 回复）
            reply = _handle_command(text, sender_id)

            # 发送回复消息（需要额外请求飞书消息 API）
            _send_text_reply(sender_id, reply, message_id)

    return jsonify({}), 200


def _send_text_reply(open_id: str, text: str, root_id: str = "") -> bool:
    """发送文本回复消息给指定用户。"""
    from src.utils.feishu import _get_tenant_access_token
    import requests

    try:
        token = _get_tenant_access_token()
        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
        payload = {
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        result = resp.json()
        if result.get("code") == 0:
            logger.info(f"✅ 已回复消息到 {open_id}")
            return True
        else:
            logger.error(f"❌ 回复消息失败: {result}")
            return False
    except Exception as e:
        logger.error(f"❌ 回复消息异常: {e}")
        return False


# ─── 启动入口 ───

def main():
    import argparse
    parser = argparse.ArgumentParser(description="GEO 论文助手 · 飞书 Webhook 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="监听端口 (默认 5000)")
    args = parser.parse_args()

    logger.info(f"🌐 飞书 Webhook 服务启动: http://{args.host}:{args.port}")
    logger.info(f"   回调地址: http://<your-domain>:{args.port}/feishu/webhook")
    app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
