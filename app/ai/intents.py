"""Lightweight intent classification and intent slot schema."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.llm.client import LLMClient


FITNESS_INTENTS = {
    "recommend_exercise",
    "generate_workout",
    "exercise_explanation",
    "exercise_substitution",
    "workout_adjustment",
}


INTENT_SCHEMA: dict[str, dict[str, list[str]]] = {
    "recommend_exercise": {
        "required_slots": ["goal", "target_body_part"],
        "optional_slots": ["equipment", "experience_level", "injury_constraints", "injuries"],
    },
    "generate_workout": {
        "required_slots": ["goal", "equipment"],
        "optional_slots": ["target_body_part", "time", "location", "injuries", "experience_level"],
    },
    "exercise_explanation": {
        "required_slots": [],
        "optional_slots": ["target_body_part", "equipment", "injuries"],
    },
    "exercise_substitution": {
        "required_slots": ["target_body_part"],
        "optional_slots": ["equipment", "goal", "injuries"],
    },
    "workout_adjustment": {
        "required_slots": ["goal"],
        "optional_slots": ["equipment", "time", "location", "injuries"],
    },
}


@dataclass
class IntentResult:
    intent: str
    confidence: float
    sub_intent: str = ""
    candidate_intents: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def known(self) -> bool:
        return self.intent not in {"unknown", "ambiguous", ""}

    @property
    def ambiguous(self) -> bool:
        return self.intent == "ambiguous" or (
            len(self.candidate_intents) >= 2 and self.confidence < 0.65
        )

    def model_dump(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "sub_intent": self.sub_intent,
            "candidate_intents": list(self.candidate_intents),
            "reason": self.reason,
        }


class LightweightIntentClassifier:
    """Rule-first classifier with optional small-model fallback."""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def classify(self, message: str) -> IntentResult:
        ruled = self._rule_classify(message)
        if ruled.confidence >= 0.75 or ruled.ambiguous:
            return ruled
        modeled = self._model_classify(message)
        if modeled:
            return modeled
        return ruled

    def resolve_clarification(self, message: str, candidate_intents: list[str]) -> IntentResult:
        text = message or ""
        candidates = [item for item in candidate_intents if item]
        if "recommend_exercise" in candidates and re.search(r"动作|一个|具体|推荐", text):
            return IntentResult("recommend_exercise", 0.9, "fitness.recommend_exercise", candidates, "clarified_by_user")
        if "generate_workout" in candidates and re.search(r"计划|一套|安排|训练", text):
            return IntentResult("generate_workout", 0.9, "fitness.generate_workout", candidates, "clarified_by_user")
        classified = self.classify(message)
        if classified.intent in candidates:
            return classified
        return IntentResult("ambiguous", 0.5, "", candidates, "clarification_still_ambiguous")

    def _rule_classify(self, message: str) -> IntentResult:
        text = (message or "").strip()
        if not text:
            return IntentResult("unknown", 0.0, "", [], "empty_message")

        venue_query = (
            re.search(r"场馆|哪里练|运动场|MediaPipe|mediapipe|关键点|动作库|动作列表|新增动作|修改动作|删除动作", text)
            or ("健身房" in text and re.search(r"附近|哪里|在哪|找|推荐|位置|地址", text))
        )
        if (
            ("天气" in text and re.search(r"查|查询|怎么样|如何|适合|能不能|可以", text))
            or venue_query
        ):
            return IntentResult("tool_request", 0.9, "tools", ["tool_request"], "tool_keyword")
        if re.search(r"报告|周报|月报|总结|复盘", text):
            return IntentResult("report", 0.9, "report", ["report"], "report_keyword")
        if re.search(r"鼓励|激励|没动力|坚持不下去|打气", text):
            return IntentResult("motivate", 0.9, "motivate", ["motivate"], "motivation_keyword")
        if re.search(r"评估|纠错|动作对不对|姿势", text):
            return IntentResult("evaluate", 0.88, "evaluate", ["evaluate"], "evaluation_keyword")
        if re.search(r"为什么|原理|知识|怎么保护|疼怎么办|痛怎么办", text):
            return IntentResult("graphrag", 0.82, "knowledge", ["graphrag"], "knowledge_keyword")

        if re.search(r"替换|换一个|替代", text):
            return IntentResult("exercise_substitution", 0.88, "fitness.exercise_substitution", ["exercise_substitution"], "substitution_keyword")
        if re.search(r"太难|太轻|太累|调整|改一下|加量|减量", text):
            return IntentResult("workout_adjustment", 0.86, "fitness.workout_adjustment", ["workout_adjustment"], "adjustment_keyword")
        if re.search(r"怎么做|标准|讲解|解释|要领", text) and "动作" in text:
            return IntentResult("exercise_explanation", 0.86, "fitness.exercise_explanation", ["exercise_explanation"], "explanation_keyword")
        if re.search(r"推荐.*动作|动作.*推荐|推荐个动作|推荐一个.*动作|练.*动作|哑铃动作|徒手动作", text):
            return IntentResult("recommend_exercise", 0.9, "fitness.recommend_exercise", ["recommend_exercise"], "exercise_recommend_keyword")
        if re.search(r"训练计划|制定.*训练|安排.*训练|一套训练|训练方案|健身计划", text):
            return IntentResult("generate_workout", 0.86, "fitness.generate_workout", ["generate_workout"], "workout_plan_keyword")
        if re.search(r"弄个训练|搞个训练|来个训练|帮我训练", text):
            return IntentResult(
                "ambiguous",
                0.52,
                "fitness",
                ["recommend_exercise", "generate_workout"],
                "fitness_request_needs_scope",
            )
        if re.search(r"训练|健身|运动|推荐|减脂|减肥|增肌|塑形|练胸|练背|练腿|康复|恢复|随便练练", text):
            return IntentResult(
                "ambiguous",
                0.58,
                "fitness",
                ["recommend_exercise", "generate_workout"],
                "broad_fitness_keyword",
            )
        return IntentResult("unknown", 0.2, "", [], "no_supported_keyword")

    def _model_classify(self, message: str) -> IntentResult | None:
        prompt = (
            "你是健身系统的轻量意图分类器，只返回 JSON。"
            '格式：{"intent":"...","confidence":0.0,"sub_intent":"...","candidate_intents":[],"reason":"..."}。'
            "可选 intent：recommend_exercise, generate_workout, exercise_explanation, "
            "exercise_substitution, workout_adjustment, evaluate, motivate, report, "
            "graphrag, tool_request, unknown。\n"
            f"用户输入：{message}\n"
        )
        try:
            raw = self.llm.invoke(prompt)
            payload = self._parse_json(raw)
        except Exception:
            return None
        intent = str(payload.get("intent") or "unknown")
        candidates = payload.get("candidate_intents") or []
        if not isinstance(candidates, list):
            candidates = []
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        return IntentResult(
            intent=intent,
            confidence=max(0.0, min(1.0, confidence)),
            sub_intent=str(payload.get("sub_intent") or ""),
            candidate_intents=[str(item) for item in candidates],
            reason=str(payload.get("reason") or "model_classifier"),
        )

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        content = (text or "").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.S | re.I).strip()
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("classifier response missing json")
        payload = json.loads(content[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("classifier response is not object")
        return payload


def required_slots_for_intent(intent: str) -> list[str]:
    return list(INTENT_SCHEMA.get(intent, {}).get("required_slots") or [])


def business_route_for_intent(intent: str) -> str:
    if intent in FITNESS_INTENTS:
        return "recommend"
    if intent == "tool_request":
        return "tools"
    if intent in {"evaluate", "motivate", "report", "graphrag"}:
        return intent
    return "fallback"
