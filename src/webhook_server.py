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

当前日期: {today}

意图类型：
- "push": 用户想要推送/获取论文日报
- "search": 用户想要搜索/查找论文
- "help": 用户询问功能或请求帮助
- "unknown": 无法识别

日期计算（仅 push 意图需要。根据当前日期计算出用户想要的日期，返回 "YYYY-MM-DD" 格式）：
- "今天"、"今日" → {today}
- "昨天"、"昨日" → {yesterday}
- "最近"、"最新"（未指定日期）→ 返回空字符串 ""
- "前天" → {day_before_yesterday}
- "上周一/二/三/四/五/六/日" → 推算出对应的日期
- "这个周一/二/..."、"本周一/二/..." → 推算出对应的日期
- "X月X号" / "X月X日" → 对应日期（年份为当前年份）
- "X月X日之前的论文"、"X月X日有什么论文" → push（不是搜索！用论文日报回答）
- "X月X日有哪些论文" → push
- "7月1日呢"、"7月2号呢" → push
- 搜索请求无需日期 → "none"

★ 核心判断规则 ★：
- 只要用户提到具体日期（X月X日、X月X号）并问论文 → push
- 只有明确说"搜索XXX"、"找一下XXX关键词"、"有没有关于XXX的论文" → search
- "X月X日的论文"/"X月X日有什么"/"X月X日有哪些" → push，不是 search！
- "X月X日之前的论文" → push

搜索关键词（仅 search 意图需要）：
- 从用户消息中提取搜索关键词

返回格式：
{{"intent": "push|search|help|unknown", "date": "YYYY-MM-DD 或 空字符串 或 none", "search_query": "关键词或空字符串"}}"""


def _classify_intent(text: str) -> dict:
    """用 LLM 识别用户意图，动态注入当前日期以正确解析相对日期。"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    day_before = (now - timedelta(days=2)).strftime("%Y-%m-%d")

    prompt = INTENT_SYSTEM_PROMPT.format(
        today=today,
        yesterday=yesterday,
        day_before_yesterday=day_before,
    )

    try:
        result = llm.chat_json(
            system_prompt=prompt,
            user_message=text,
            temperature=0.1,
            max_tokens=128,
        )
        if not isinstance(result, dict):
            logger.warning(f"⚠️ LLM 返回非 dict 类型: {type(result).__name__}: {result}")
            return _classify_fallback(text)
        logger.info(f"🧠 意图识别: '{text}' → {result}")
        return result
    except Exception as e:
        logger.error(f"意图识别失败，回退到关键词匹配: {e}")
        logger.error(f"   异常详情: {type(e).__name__}: {e}")
        return _classify_fallback(text)


def _classify_fallback(text: str) -> dict:
    """关键词回退（LLM 调用失败时使用）。"""
    # 只在句首或明确前缀时才算搜索
    if re.match(r"^(搜索|查找|找一下|找找)\s*", text):
        query = re.sub(r"^(搜索|查找|找一下|找找)\s*", "", text)
        return {"intent": "search", "date": "none", "search_query": query}
    if any(kw in text for kw in ["帮助", "功能", "能做什么", "怎么用"]):
        return {"intent": "help", "date": "none", "search_query": ""}
    # 论文/日报/推送 相关 → push
    if any(kw in text for kw in ["推送", "论文", "日报", "看看", "有什么", "来一份", "之前", "之前"]):
        if any(kw in text for kw in ["昨天", "昨天", "昨日"]):
            return {"intent": "push", "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"), "search_query": ""}
        if any(kw in text for kw in ["今天", "今天", "今日"]):
            return {"intent": "push", "date": datetime.now().strftime("%Y-%m-%d"), "search_query": ""}
        return {"intent": "push", "date": "", "search_query": ""}
    return {"intent": "unknown", "date": "none", "search_query": ""}


# ─── 命令处理 ───

def _handle_command(text: str, target_id: str, target_type: str) -> str:
    """解析用户消息，执行对应的操作，返回回复文本。

    Args:
        text: 用户消息文本
        target_id: 飞书目标 ID（群聊为 chat_id，私聊为 open_id）
        target_type: "chat_id" 或 "open_id"
    """
    intent = _classify_intent(text)
    # 防止 LLM 返回残缺 JSON 导致 KeyError
    intent.setdefault("intent", "unknown")
    intent.setdefault("date", "none")
    intent.setdefault("search_query", "")

    # 推送论文
    if intent["intent"] == "push":
        raw_date = intent.get("date", "").strip()
        if raw_date and raw_date != "none":
            target = raw_date
            label = f"论文日报（{target}）"
        else:
            target = None
            label = "最近论文日报"

        logger.info(f"📨 推送请求: {label} → {target_type}={target_id}")
        try:
            run_pipeline(target_date=target, feishu_chat_id=target_id, feishu_chat_type=target_type)
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
            chat_id = event.get("message", {}).get("chat_id", "")

            # 判断消息来源
            is_group = chat_id and chat_id != sender_id
            target_id = chat_id if is_group else sender_id
            target_type = "chat_id" if is_group else "open_id"

            logger.info(f"📨 收到消息: '{text}' from {sender_id} (chat={chat_id}, {'群聊' if is_group else '私聊'})")

            # 处理命令并回复
            reply = _handle_command(text, target_id, target_type)

            # 发送回复消息
            _send_text_reply(target_id, reply, message_id, target_type)

    return jsonify({}), 200


def _send_text_reply(target_id: str, text: str, root_id: str = "", target_type: str = "open_id") -> bool:
    """发送文本回复消息（群聊回复到群，私聊回复到人）。"""
    from src.utils.feishu import _get_tenant_access_token
    import requests

    try:
        token = _get_tenant_access_token()
        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={target_type}"
        payload = {
            "receive_id": target_id,
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
            logger.info(f"✅ 已回复消息到 {target_type}={target_id}")
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
