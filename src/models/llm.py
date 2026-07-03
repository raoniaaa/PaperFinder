"""豆包 LLM 客户端封装（OpenAI 兼容模式）。"""

import json
from typing import Optional
from openai import OpenAI
from src.config import ARK_API_KEY, ARK_BASE_URL, ARK_MODEL_ID
from src.utils.logger import logger


class DoubaoLLM:
    """火山引擎 Ark API 的豆包模型客户端。"""

    def __init__(
        self,
        api_key: str = ARK_API_KEY,
        base_url: str = ARK_BASE_URL,
        model_id: str = ARK_MODEL_ID,
    ):
        self.model_id = model_id
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """普通对话，返回文本响应。"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or ""
            return content
        except Exception as e:
            logger.error(f"LLM chat 调用失败: {e}")
            raise

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> dict:
        """结构化 JSON 输出，返回解析后的 dict。"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"LLM JSON 解析失败: {e}, content={content[:200]}")
            return {}
        except Exception as e:
            logger.error(f"LLM JSON 调用失败: {e}")
            raise


# 全局单例
llm = DoubaoLLM()
