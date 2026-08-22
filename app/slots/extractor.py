"""Slot extraction using the shared LLMClient with deterministic fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.client import LLMClient
from app.slots.models import SlotState


class SlotExtractor:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def extract(self, message: str, *, history: list[dict[str, Any]] | None = None, state: SlotState | None = None) -> dict[str, Any]:
        state = state or SlotState()
        prompt = self._build_prompt(message, history or [], state)
        extracted = self._llm_extract(prompt)
        if not extracted:
            extracted = self._rule_extract(message)
        return self._normalize(extracted)

    def _build_prompt(self, message: str, history: list[dict[str, Any]], state: SlotState) -> str:
        return (
            "你是健身对话槽位抽取器。只返回 JSON。"
            '格式：{"goal": "...", "target_body_part": "...", "injuries": ["..."], "equipment": "...", "time": "...", "location": "...", "missing": ["..."]}\n'
            f"已有槽位：{json.dumps(state.model_dump(mode='json'), ensure_ascii=False)}\n"
            f"历史消息：{json.dumps(history[-8:], ensure_ascii=False)}\n"
            f"当前用户消息：{message}\n"
            "槽位候选值：goal=减脂/增肌/塑形/康复/综合；target_body_part=胸/背/腿/臀/肩/手臂/核心/全身；"
            "injuries=膝/踝/腰/肩/腕/无；equipment=徒手/弹力带/哑铃/健身房器械；time=早上/午间/晚上；location=家里/健身房/户外。"
        )

    def _llm_extract(self, prompt: str) -> dict[str, Any] | None:
        try:
            raw = self.llm.invoke(prompt)
        except Exception:
            return None
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S | re.I).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _rule_extract(self, message: str) -> dict[str, Any]:
        text = message or ""
        payload: dict[str, Any] = {}
        if re.search(r"减脂|减肥|瘦身|fat\s*loss", text, re.I):
            payload["goal"] = "减脂"
        elif re.search(r"增肌|力量|肌肉|build muscle", text, re.I):
            payload["goal"] = "增肌"
        elif re.search(r"塑形|线条|身材", text, re.I):
            payload["goal"] = "塑形"
        elif re.search(r"康复|恢复|受伤|膝盖不好|腰痛|肩痛", text, re.I):
            payload["goal"] = "康复"
        if re.search(r"膝|膝盖|knee", text, re.I):
            payload.setdefault("injuries", []).append("膝")
        if re.search(r"踝|脚踝|ankle", text, re.I):
            payload.setdefault("injuries", []).append("踝")
        if re.search(r"腰|lower back", text, re.I):
            payload.setdefault("injuries", []).append("腰")
        if re.search(r"肩|shoulder", text, re.I):
            payload.setdefault("injuries", []).append("肩")
        if re.search(r"腕|手腕|wrist", text, re.I):
            payload.setdefault("injuries", []).append("腕")
        if re.search(r"无伤病|没有伤|无问题|没问题", text, re.I):
            payload["injuries"] = ["无"]
        if re.search(r"胸|胸部|chest", text, re.I):
            payload["target_body_part"] = "胸"
        elif re.search(r"背|背部|back", text, re.I):
            payload["target_body_part"] = "背"
        elif re.search(r"腿|腿部|下肢|leg", text, re.I):
            payload["target_body_part"] = "腿"
        elif re.search(r"臀|臀部|glute", text, re.I):
            payload["target_body_part"] = "臀"
        elif re.search(r"肩|肩部|shoulder", text, re.I):
            payload["target_body_part"] = "肩"
        elif re.search(r"手臂|胳膊|arm", text, re.I):
            payload["target_body_part"] = "手臂"
        elif re.search(r"核心|腹|腹部|core", text, re.I):
            payload["target_body_part"] = "核心"
        elif re.search(r"全身|全身性|full body", text, re.I):
            payload["target_body_part"] = "全身"
        if re.search(r"徒手|无器材|没器材|bodyweight", text, re.I):
            payload["equipment"] = "徒手"
        elif re.search(r"弹力带", text, re.I):
            payload["equipment"] = "弹力带"
        elif re.search(r"哑铃", text, re.I):
            payload["equipment"] = "哑铃"
        elif re.search(r"健身房|器械|gym", text, re.I):
            payload["equipment"] = "健身房器械"
        if re.search(r"早上|晨练|早晨", text, re.I):
            payload["time"] = "早上"
        elif re.search(r"午间|中午", text, re.I):
            payload["time"] = "午间"
        elif re.search(r"晚上|夜间|晚饭后", text, re.I):
            payload["time"] = "晚上"
        if re.search(r"家里|在家|居家", text, re.I):
            payload["location"] = "家里"
        elif re.search(r"健身房|器械房", text, re.I):
            payload["location"] = "健身房"
        elif re.search(r"户外|室外", text, re.I):
            payload["location"] = "户外"
        return payload

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = SlotState(**payload)
        normalized = state.model_dump(mode="json", exclude_none=True)
        return {
            key: normalized[key]
            for key in SlotState.slot_names()
            if key in normalized and normalized[key] not in (None, [], "")
        }
