from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


class AIProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    model: str
    api_key: str
    base_url: str


class UnifiedLLM:
    """Small OpenAI-compatible client with per-request provider/model switching."""

    PROVIDERS = {
        "deepseek": ("AI_DEEPSEEK_API_KEY", "AI_DEEPSEEK_BASE_URL", "https://api.deepseek.com", "deepseek-v4-flash"),
        "dashscope": (
            "AI_DASHSCOPE_API_KEY",
            "AI_DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen-plus",
        ),
    }
    ALIASES = {"bailian": "dashscope", "aliyun": "dashscope", "qwen": "dashscope"}

    def resolve(self, provider: str | None = None, model: str | None = None) -> Provider:
        name = (provider or os.getenv("AI_LLM_PROVIDER", "deepseek")).strip().lower()
        name = self.ALIASES.get(name, name)
        if name not in self.PROVIDERS:
            raise AIProviderError(f"不支持的模型供应商：{name}")
        key_env, url_env, default_url, default_model = self.PROVIDERS[name]
        legacy_key_env = "DEEPSEEK_API_KEY" if name == "deepseek" else "DASHSCOPE_API_KEY"
        return Provider(
            name=name,
            model=(model or os.getenv("AI_MODEL_NAME") or default_model).strip(),
            api_key=(os.getenv(key_env) or os.getenv(legacy_key_env) or "").strip(),
            base_url=os.getenv(url_env, default_url).rstrip("/"),
        )

    def available(self) -> list[dict[str, Any]]:
        result = []
        for name in self.PROVIDERS:
            config = self.resolve(name)
            result.append({"provider": name, "default_model": config.model, "configured": bool(config.api_key)})
        return result

    def chat(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> str:
        config = self.resolve(provider, model)
        if not config.api_key:
            raise AIProviderError(f"{config.name} 未配置 API Key")
        try:
            response = httpx.post(
                f"{config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False,
                },
                timeout=float(os.getenv("AI_LLM_TIMEOUT", "45")),
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError(f"{config.name} 调用失败：{exc}") from exc

    def test_connection(self, provider: str, model: str | None = None) -> dict[str, Any]:
        config = self.resolve(provider, model)
        started = time.perf_counter()
        answer = self.chat(
            [
                {"role": "system", "content": "你是接口连通性测试助手。"},
                {"role": "user", "content": "只回复：连接成功"},
            ],
            config.name,
            config.model,
            temperature=0,
        )
        return {
            "ok": True,
            "provider": config.name,
            "model": config.model,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "response": answer[:100],
        }
