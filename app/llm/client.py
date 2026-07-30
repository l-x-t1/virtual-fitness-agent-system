from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


class LLMError(RuntimeError):
    """Base exception for failures that are safe to expose to callers."""


class LLMConfigurationError(LLMError):
    """Raised when the selected provider is unsupported or not configured."""


class LLMInvocationError(LLMError):
    """Raised when an online model request fails after the configured retries."""


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    model: str
    api_key: str = field(repr=False)
    base_url: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


class LLMClient:
    """Unified OpenAI-compatible client for DeepSeek and DashScope/Bailian."""

    DEFAULTS = {
        "deepseek": {
            "model": "deepseek-v4-flash",
            "api_key": "DEEPSEEK_API_KEY",
            "base_url": "DEEPSEEK_BASE_URL",
            "base_url_default": "https://api.deepseek.com",
        },
        "dashscope": {
            "model": "qwen-plus",
            "api_key": "DASHSCOPE_API_KEY",
            "base_url": "DASHSCOPE_BASE_URL",
            "base_url_default": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
    }
    PROVIDER_ALIASES = {
        "deepseek": "deepseek",
        "deepseek-chat": "deepseek",
        "dashscope": "dashscope",
        "qwen": "dashscope",
        "bailian": "dashscope",
        "aliyun": "dashscope",
    }

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        environ: Mapping[str, str] | None = None,
        chat_model: Any | None = None,
    ):
        env = os.environ if environ is None else environ
        self.config = self._resolve_config(env, provider, model, api_key, base_url)
        self.temperature = self._float_value(
            temperature if temperature is not None else env.get("LLM_TEMPERATURE", "0.2"),
            "LLM_TEMPERATURE",
        )
        self.timeout = self._float_value(
            timeout if timeout is not None else env.get("LLM_TIMEOUT", "60"),
            "LLM_TIMEOUT",
        )
        self.max_retries = self._retry_value(
            max_retries if max_retries is not None else env.get("LLM_MAX_RETRIES", "2")
        )
        self._model: Any | None = chat_model

    @property
    def provider(self) -> str:
        return self.config.provider

    @property
    def model_name(self) -> str:
        return self.config.model

    @property
    def configured(self) -> bool:
        return self.config.configured

    @property
    def mode(self) -> str:
        return "online" if self.configured else "fallback"

    def chat(self, messages: list[dict[str, Any] | BaseMessage | tuple[str, str]]) -> str:
        converted = [self._to_message(message) for message in messages]
        try:
            response = self._chat_model().invoke(converted)
        except LLMConfigurationError:
            raise
        except Exception:
            raise LLMInvocationError(
                f"LLM request failed for provider '{self.config.provider}'."
            ) from None
        return str(response.content)

    async def achat(self, messages: list[dict[str, Any] | BaseMessage | tuple[str, str]]) -> str:
        converted = [self._to_message(message) for message in messages]
        try:
            response = await self._chat_model().ainvoke(converted)
        except LLMConfigurationError:
            raise
        except Exception:
            raise LLMInvocationError(
                f"LLM request failed for provider '{self.config.provider}'."
            ) from None
        return str(response.content)

    def invoke(self, prompt: str) -> str:
        return self.chat([HumanMessage(content=prompt)])

    async def ainvoke(self, prompt: str) -> str:
        return await self.achat([HumanMessage(content=prompt)])

    def _chat_model(self) -> Any:
        if self._model is None:
            if not self.config.api_key:
                env_name = self.DEFAULTS[self.config.provider]["api_key"]
                raise LLMConfigurationError(
                    f"{env_name} is required when LLM_PROVIDER={self.config.provider}."
                )
            self._model = ChatOpenAI(
                model=self.config.model,
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                temperature=self.temperature,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        return self._model

    def _resolve_config(
        self,
        env: Mapping[str, str],
        provider: str | None,
        model: str | None,
        api_key: str | None,
        base_url: str | None,
    ) -> LLMProviderConfig:
        requested = (provider or env.get("LLM_PROVIDER") or "deepseek").strip().lower()
        selected_provider = self.PROVIDER_ALIASES.get(requested)
        if selected_provider is None:
            raise LLMConfigurationError(f"Unsupported LLM_PROVIDER: {requested}")

        defaults = self.DEFAULTS[selected_provider]
        selected_model = (model or env.get("MODEL_NAME") or defaults["model"]).strip()
        selected_key = api_key if api_key is not None else env.get(defaults["api_key"], "")
        selected_url = (
            base_url
            if base_url is not None
            else env.get(defaults["base_url"], "")
        ) or defaults["base_url_default"]
        return LLMProviderConfig(
            provider=selected_provider,
            model=selected_model or defaults["model"],
            api_key=selected_key.strip(),
            base_url=selected_url.strip().rstrip("/"),
        )

    def _to_message(self, message: dict[str, Any] | BaseMessage | tuple[str, str]) -> BaseMessage:
        if isinstance(message, BaseMessage):
            return message
        if isinstance(message, tuple):
            role, content = message
        else:
            role = str(message.get("role", "user"))
            content = str(message.get("content", ""))
        role = role.lower()
        if role in {"system", "developer"}:
            return SystemMessage(content=content)
        if role in {"assistant", "ai"}:
            return AIMessage(content=content)
        return HumanMessage(content=content)

    def _float_value(self, value: Any, name: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            raise LLMConfigurationError(f"{name} must be a number.") from None
        if parsed <= 0 and name == "LLM_TIMEOUT":
            raise LLMConfigurationError("LLM_TIMEOUT must be greater than zero.")
        return parsed

    def _retry_value(self, value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise LLMConfigurationError("LLM_MAX_RETRIES must be an integer.") from None
        if parsed < 0 or parsed > 5:
            raise LLMConfigurationError("LLM_MAX_RETRIES must be between 0 and 5.")
        return parsed
