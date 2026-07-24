from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings


class LLMConfigurationError(RuntimeError):
    """Raised when the selected LLM provider is missing required configuration."""


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    model: str
    api_key: str
    base_url: str


class LLMClient:
    """Unified LangChain-backed client for DeepSeek and DashScope compatible chat models."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
    ):
        self.config = self._resolve_config(provider, model)
        self.temperature = settings.llm_temperature if temperature is None else temperature
        self.timeout = settings.llm_timeout if timeout is None else timeout
        self._model: ChatOpenAI | None = None

    def chat(self, messages: list[dict[str, Any] | BaseMessage | tuple[str, str]]) -> str:
        response = self._chat_model().invoke([self._to_message(message) for message in messages])
        return str(response.content)

    def invoke(self, prompt: str) -> str:
        return self.chat([HumanMessage(content=prompt)])

    def _chat_model(self) -> ChatOpenAI:
        if self._model is None:
            if not self.config.api_key:
                env_name = "DEEPSEEK_API_KEY" if self.config.provider == "deepseek" else "DASHSCOPE_API_KEY"
                raise LLMConfigurationError(f"{env_name} is required when LLM_PROVIDER={self.config.provider}.")
            self._model = ChatOpenAI(
                model=self.config.model,
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                temperature=self.temperature,
                timeout=self.timeout,
                max_retries=1,
            )
        return self._model

    def _resolve_config(self, provider: str | None, model: str | None) -> LLMProviderConfig:
        selected_provider = (provider or settings.llm_provider).strip().lower()
        selected_model = (model or settings.model_name).strip()

        if selected_provider in {"deepseek", "deepseek-chat"}:
            return LLMProviderConfig(
                provider="deepseek",
                model=selected_model or "deepseek-chat",
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )

        if selected_provider in {"dashscope", "qwen", "bailian", "aliyun"}:
            return LLMProviderConfig(
                provider="dashscope",
                model=selected_model or "qwen-plus",
                api_key=settings.dashscope_api_key,
                base_url=settings.dashscope_base_url,
            )

        raise LLMConfigurationError(f"Unsupported LLM_PROVIDER: {selected_provider}")

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
