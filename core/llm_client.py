# core/llm_client.py
import os
import sys
import logging
from openai import OpenAI

# 将项目根目录添加到 sys.path，确保能 import 到 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        llm_config = config.LLM_CONFIG
        provider = llm_config["provider"]  # "local" 或 "cloud"

        # 根据 provider 读取对应配置
        provider_config = llm_config[provider]

        # 环境变量优先覆盖配置文件中的 api_key
        api_key = os.getenv("DASHSCOPE_API_KEY") or provider_config.get("api_key", "not-needed")

        self.client = OpenAI(
            base_url=provider_config["base_url"],
            api_key=api_key,
        )
        self.model = provider_config["model"]
        self.provider = provider

        logger.info(f"LLM初始化完成 | 模式: {provider} | 模型: {self.model}")

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM调用失败 [{self.provider}]: {e}")
            return f"报告生成失败: {e}"


# 全局单例
llm = LLMClient()