from __future__ import annotations

import json
from typing import Any

from app.llm.client import LLMClient
from app.tools.registry import ToolRegistry, tool_result


class FitnessToolAgent:
    """Lets the existing LLM Tool Loop select tools, with deterministic offline fallback."""

    def __init__(self, registry: ToolRegistry, llm_client: LLMClient | Any | None = None):
        self.registry = registry
        self.llm_client = llm_client or LLMClient()

    def run(self, question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        self.registry.results.clear()
        prompt = (
            "你是健身工具智能体。根据用户问题自主选择一个或多个已绑定工具。"
            "需要写入或删除动作时必须遵守工具权限和 confirm 约束。"
            "最后基于工具返回简洁回答，不得把 mock 数据描述为实时真实数据。\n"
            f"上下文：{json.dumps(context or {}, ensure_ascii=False, default=str)}\n"
            f"问题：{question}"
        )
        try:
            answer = self.llm_client.bind_tools(self.registry.specs()).invoke(prompt)
            return {
                "answer": answer,
                "tool_results": list(self.registry.results),
                "mode": "online",
                "fallback_reason": None,
            }
        except Exception:
            return self._fallback(question, context or {})

    async def arun(self, question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        self.registry.results.clear()
        try:
            prompt = f"根据问题自主选择已绑定工具并回答：{question}\n上下文：{json.dumps(context or {}, ensure_ascii=False, default=str)}"
            answer = await self.llm_client.bind_tools(self.registry.specs()).ainvoke(prompt)
            return {"answer": answer, "tool_results": list(self.registry.results), "mode": "online", "fallback_reason": None}
        except Exception:
            return self._fallback(question, context or {})

    def _fallback(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        text = str(question or "")
        if "天气" in text:
            name, args = "get_weather", {"location": context.get("location") or self._location(text)}
        elif any(word in text for word in ("场馆", "健身房", "哪里练", "运动场")):
            name, args = "recommend_venues", {"exercise_name": context.get("exercise_name"), "preference": context.get("preference")}
        elif any(word in text for word in ("姿态", "姿势", "关键点", "动作评估", "纠错")):
            name, args = "evaluate_pose", {"exercise_name": context.get("exercise_name") or "未知动作", "landmarks": context.get("landmarks") or [], "raw_score": context.get("raw_score")}
        elif any(word in text for word in ("动作库", "动作列表", "有哪些动作")):
            name, args = "list_exercises", {"query": context.get("query") or ""}
        else:
            return {"answer": "当前问题没有匹配到可用健身工具。", "tool_results": [], "mode": "fallback", "fallback_reason": "no_matching_tool"}
        result = self.registry.call(name, **args)
        return {
            "answer": self._answer(name, result),
            "tool_results": list(self.registry.results),
            "mode": "fallback",
            "fallback_reason": "llm_unavailable",
        }

    def _location(self, text: str) -> str:
        cleaned = text.replace("天气", "").replace("怎么样", "").replace("如何", "").strip(" ？?")
        return cleaned or "当前位置"

    def _answer(self, name: str, result: dict[str, Any]) -> str:
        if not result.get("ok"):
            return f"工具 {name} 暂时无法完成请求（{result.get('fallback_reason')}）。"
        mode_note = "演示数据" if result.get("mode") == "mock" else "可用数据"
        return f"工具 {name} 已返回{mode_note}。"
