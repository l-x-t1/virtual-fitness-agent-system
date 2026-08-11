from __future__ import annotations

import inspect
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
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
    def name(self) -> str:
        return self.provider

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str | None = None


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
        max_tool_rounds: int | None = None,
        environ: Mapping[str, str] | None = None,
        chat_model: Any | None = None,
        tools: list[Any] | None = None,
        tool_choice: str | None = None,
    ):
        env = os.environ if environ is None else environ
        self._environ = env
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
        self.max_tool_rounds = self._tool_round_value(
            max_tool_rounds if max_tool_rounds is not None else env.get("LLM_TOOL_MAX_ROUNDS", "6")
        )
        self._model: Any | None = chat_model
        self._tools: list[ToolSpec] = self._normalize_tools(tools)
        self._tool_choice = tool_choice

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

    def bind_tools(self, tools: list[Any] | None, *, tool_choice: str | None = None) -> LLMClient:
        clone = self._clone()
        clone._tools = clone._normalize_tools(tools)
        clone._tool_choice = tool_choice
        return clone

    def resolve(self, provider: str | None = None, model: str | None = None) -> LLMProviderConfig:
        if provider is None and model is None:
            return self.config
        return self._resolve_config(self._environ, provider, model, None, None)

    def available(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for provider in self.DEFAULTS:
            config = self.resolve(provider)
            result.append(
                {
                    "provider": config.provider,
                    "default_model": config.model,
                    "configured": config.configured,
                }
            )
        return result

    def test_connection(self, provider: str, model: str | None = None) -> dict[str, Any]:
        import time

        config = self.resolve(provider, model)
        started = time.perf_counter()
        answer = self.chat(
            [
                {"role": "system", "content": "你是接口连通性测试助手。"},
                {"role": "user", "content": "只回复：连接成功"},
            ],
            provider=config.provider,
            model=config.model,
            temperature=0,
        )
        return {
            "ok": True,
            "provider": config.provider,
            "model": config.model,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "response": answer[:100],
        }

    def chat(
        self,
        messages: list[dict[str, Any] | BaseMessage | tuple[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        *,
        tools: list[Any] | None = None,
    ) -> str:
        client = self._request_client(provider, model, temperature)
        converted = [self._to_message(message) for message in messages]
        try:
            response = client._invoke_messages(converted, tools=tools)
        except LLMConfigurationError:
            raise
        except LLMInvocationError:
            raise
        except Exception:
            raise LLMInvocationError(
                f"LLM request failed for provider '{self.config.provider}'."
            ) from None
        return self._content_text(response)

    async def achat(
        self,
        messages: list[dict[str, Any] | BaseMessage | tuple[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        *,
        tools: list[Any] | None = None,
    ) -> str:
        client = self._request_client(provider, model, temperature)
        converted = [self._to_message(message) for message in messages]
        try:
            response = await client._ainvoke_messages(converted, tools=tools)
        except LLMConfigurationError:
            raise
        except LLMInvocationError:
            raise
        except Exception:
            raise LLMInvocationError(
                f"LLM request failed for provider '{self.config.provider}'."
            ) from None
        return self._content_text(response)

    def invoke(self, prompt: str, *, tools: list[Any] | None = None) -> str:
        return self.chat([HumanMessage(content=prompt)], tools=tools)

    async def ainvoke(self, prompt: str, *, tools: list[Any] | None = None) -> str:
        return await self.achat([HumanMessage(content=prompt)], tools=tools)

    def stream_chat(
        self,
        messages: list[dict[str, Any] | BaseMessage | tuple[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ):
        client = self._request_client(provider, model, temperature)
        converted = [client._to_message(message) for message in messages]
        try:
            for chunk in client._chat_model().stream(converted):
                text = client._content_text(chunk)
                if text:
                    yield text
        except LLMConfigurationError:
            raise
        except LLMInvocationError:
            raise
        except Exception:
            raise LLMInvocationError(
                f"LLM stream request failed for provider '{client.config.provider}'."
            ) from None

    async def astream_chat(
        self,
        messages: list[dict[str, Any] | BaseMessage | tuple[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ):
        client = self._request_client(provider, model, temperature)
        converted = [client._to_message(message) for message in messages]
        try:
            async for chunk in client._chat_model().astream(converted):
                text = client._content_text(chunk)
                if text:
                    yield text
        except LLMConfigurationError:
            raise
        except LLMInvocationError:
            raise
        except Exception:
            raise LLMInvocationError(
                f"LLM async stream request failed for provider '{client.config.provider}'."
            ) from None

    def _clone(self) -> LLMClient:
        clone = self.__class__(
            provider=self.config.provider,
            model=self.config.model,
            api_key=self.config.api_key or None,
            base_url=self.config.base_url,
            temperature=self.temperature,
            timeout=self.timeout,
            max_retries=self.max_retries,
            max_tool_rounds=self.max_tool_rounds,
            chat_model=self._model,
        )
        clone._tools = list(self._tools)
        clone._tool_choice = self._tool_choice
        return clone

    def _request_client(
        self,
        provider: str | None,
        model: str | None,
        temperature: float | None,
    ) -> LLMClient:
        requested_provider = self.PROVIDER_ALIASES.get(provider.strip().lower(), provider.strip().lower()) if provider else None
        same_provider = requested_provider in {None, self.config.provider}
        same_model = model in {None, self.config.model}
        same_temperature = temperature is None or float(temperature) == self.temperature
        if same_provider and same_model and same_temperature:
            return self

        config = self.resolve(requested_provider or self.config.provider, model or self.config.model)
        clone = self.__class__(
            provider=config.provider,
            model=config.model,
            api_key=config.api_key or None,
            base_url=config.base_url,
            temperature=self.temperature if temperature is None else float(temperature),
            timeout=self.timeout,
            max_retries=self.max_retries,
            max_tool_rounds=self.max_tool_rounds,
        )
        clone._tools = list(self._tools)
        clone._tool_choice = self._tool_choice
        return clone

    def _base_model(self) -> Any:
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

    def _chat_model(self, tools: list[ToolSpec] | None = None) -> Any:
        base = self._base_model()
        active_tools = self._normalize_tools(tools if tools is not None else self._tools)
        if not active_tools:
            return base
        binder = getattr(base, "bind_tools", None)
        if not callable(binder):
            return base
        try:
            if self._tool_choice is not None:
                return binder([tool.handler for tool in active_tools], tool_choice=self._tool_choice)
        except TypeError:
            pass
        try:
            return binder([tool.handler for tool in active_tools])
        except TypeError:
            return base

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

    def _tool_round_value(self, value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise LLMConfigurationError("LLM_TOOL_MAX_ROUNDS must be an integer.") from None
        if parsed < 1 or parsed > 12:
            raise LLMConfigurationError("LLM_TOOL_MAX_ROUNDS must be between 1 and 12.")
        return parsed

    def _normalize_tools(self, tools: list[Any] | None) -> list[ToolSpec]:
        if not tools:
            return []
        normalized: list[ToolSpec] = []
        for tool in tools:
            normalized.append(self._normalize_tool(tool))
        return normalized

    def _normalize_tool(self, tool: Any) -> ToolSpec:
        if isinstance(tool, ToolSpec):
            return tool
        if isinstance(tool, dict):
            handler = tool.get("handler") or tool.get("callable")
            if not callable(handler):
                raise LLMConfigurationError("Tool definitions must include a callable handler.")
            name = str(tool.get("name") or getattr(handler, "__name__", "tool"))
            description = str(tool.get("description") or (inspect.getdoc(handler) or name))
            parameters = dict(tool.get("parameters") or self._schema_for_callable(handler))
            return ToolSpec(name=name, description=description, handler=handler, parameters=parameters)
        if callable(tool):
            return ToolSpec(
                name=getattr(tool, "__name__", "tool"),
                description=inspect.getdoc(tool) or getattr(tool, "__name__", "tool"),
                handler=tool,
                parameters=self._schema_for_callable(tool),
            )
        raise LLMConfigurationError("Unsupported tool definition.")

    def _schema_for_callable(self, handler: Callable[..., Any]) -> dict[str, Any]:
        try:
            signature = inspect.signature(handler)
            type_hints = inspect.get_annotations(handler, eval_str=True)
        except (TypeError, ValueError):
            return {"type": "object", "properties": {}, "required": []}

        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, parameter in signature.parameters.items():
            if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
                continue
            annotation = type_hints.get(name, parameter.annotation)
            properties[name] = self._annotation_schema(annotation, parameter.default)
            if parameter.default is inspect._empty:
                required.append(name)
        return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}

    def _annotation_schema(self, annotation: Any, default: Any) -> dict[str, Any]:
        if annotation is inspect._empty or annotation is Any:
            schema: dict[str, Any] = {"type": "string"}
        else:
            origin = getattr(annotation, "__origin__", None)
            args = getattr(annotation, "__args__", ())
            if origin is list or origin is tuple:
                schema = {"type": "array"}
            elif origin is dict:
                schema = {"type": "object"}
            elif origin is None and annotation in {str, "str"}:
                schema = {"type": "string"}
            elif annotation in {int, "int"}:
                schema = {"type": "integer"}
            elif annotation in {float, "float"}:
                schema = {"type": "number"}
            elif annotation in {bool, "bool"}:
                schema = {"type": "boolean"}
            elif args and type(None) in args:
                schema = self._annotation_schema(next((item for item in args if item is not type(None)), str), default)
            else:
                schema = {"type": "string"}
        if default is not inspect._empty and default is not None:
            schema["default"] = default
        return schema

    def _invoke_messages(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[Any] | None = None,
    ) -> AIMessage:
        active_tools = self._normalize_tools(tools if tools is not None else self._tools)
        model = self._chat_model(active_tools)
        working_messages = list(messages)
        for _ in range(self.max_tool_rounds):
            response = model.invoke(working_messages)
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                return response
            working_messages.append(response)
            for call in tool_calls:
                result = self._execute_tool_call(call, active_tools)
                working_messages.append(
                    ToolMessage(
                        content=self._serialize_tool_result(result),
                        tool_call_id=call.call_id or call.name,
                        name=call.name,
                    )
                )
        raise LLMInvocationError("Tool calling exceeded the configured round limit.")

    async def _ainvoke_messages(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[Any] | None = None,
    ) -> AIMessage:
        active_tools = self._normalize_tools(tools if tools is not None else self._tools)
        model = self._chat_model(active_tools)
        working_messages = list(messages)
        for _ in range(self.max_tool_rounds):
            response = await model.ainvoke(working_messages)
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                return response
            working_messages.append(response)
            for call in tool_calls:
                result = await self._aexecute_tool_call(call, active_tools)
                working_messages.append(
                    ToolMessage(
                        content=self._serialize_tool_result(result),
                        tool_call_id=call.call_id or call.name,
                        name=call.name,
                    )
                )
        raise LLMInvocationError("Tool calling exceeded the configured round limit.")

    def _extract_tool_calls(self, response: Any) -> list[ToolCall]:
        raw_calls = getattr(response, "tool_calls", None) or getattr(
            getattr(response, "additional_kwargs", None) or {}, "get", lambda *_: None
        )("tool_calls")
        calls: list[ToolCall] = []
        if raw_calls:
            for item in raw_calls:
                calls.extend(self._normalize_tool_call(item))
        if calls:
            return calls
        content = self._content_text(response).strip()
        if not content:
            return []
        parsed = self._load_tool_payload(content)
        if not parsed:
            return []
        if isinstance(parsed, dict) and "tool_calls" in parsed:
            items = parsed["tool_calls"]
            if isinstance(items, list):
                for item in items:
                    calls.extend(self._normalize_tool_call(item))
            return calls
        if isinstance(parsed, dict) and "tool_call" in parsed:
            calls.extend(
                self._normalize_tool_call(
                    {
                        "name": parsed.get("tool_call"),
                        "arguments": parsed.get("arguments") or {},
                        "id": parsed.get("id"),
                    }
                )
            )
            return calls
        return self._normalize_tool_call(parsed)

    def _normalize_tool_call(self, item: Any) -> list[ToolCall]:
        if not isinstance(item, dict):
            return []
        name = item.get("name") or item.get("tool_call")
        if not name and isinstance(item.get("function"), dict):
            name = item["function"].get("name")
        if not name:
            return []
        arguments = item.get("args")
        if arguments is None and isinstance(item.get("function"), dict):
            arguments = item["function"].get("arguments")
        if arguments is None:
            arguments = item.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"input": arguments}
        if not isinstance(arguments, dict):
            arguments = {"input": arguments}
        call_id = item.get("id") or item.get("tool_call_id")
        return [ToolCall(name=str(name), arguments=dict(arguments), call_id=str(call_id) if call_id else None)]

    def _execute_tool_call(
        self,
        call: ToolCall,
        tools: list[ToolSpec],
    ) -> Any:
        tool = next((item for item in tools if item.name == call.name), None)
        if tool is None:
            raise LLMInvocationError(f"Unknown tool requested by the model: {call.name}")
        result = tool.handler(**call.arguments)
        if inspect.isawaitable(result):
            raise LLMInvocationError(
                f"Tool '{call.name}' returned awaitable result in synchronous mode."
            )
        return result

    async def _aexecute_tool_call(
        self,
        call: ToolCall,
        tools: list[ToolSpec],
    ) -> Any:
        tool = next((item for item in tools if item.name == call.name), None)
        if tool is None:
            raise LLMInvocationError(f"Unknown tool requested by the model: {call.name}")
        result = tool.handler(**call.arguments)
        if inspect.isawaitable(result):
            return await result
        return result

    def _serialize_tool_result(self, result: Any) -> str:
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(result)

    def _load_tool_payload(self, content: str) -> Any:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None

    def _content_text(self, response: Any) -> str:
        content = getattr(response, "content", response)
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            pieces = []
            for item in content:
                if isinstance(item, str):
                    pieces.append(item)
                elif isinstance(item, dict):
                    pieces.append(str(item.get("text") or item.get("content") or item))
                else:
                    pieces.append(str(item))
            return "".join(pieces)
        return str(content)
