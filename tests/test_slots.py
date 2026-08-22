from __future__ import annotations

import json

from app.slots.archiver import SlotArchiver
from app.slots.clarifier import SlotClarifier
from app.slots.extractor import SlotExtractor
from app.slots.models import SlotState
from app.slots.state import SlotStore
from app.slots.validator import SlotValidator


class DummyLLM:
    def __init__(self, text: str | None = None):
        self.text = text or ""

    def invoke(self, prompt: str) -> str:
        return self.text


def test_slot_state_merge_and_required():
    state = SlotState(goal="减脂", injuries=["膝"])
    merged = state.merged({"equipment": "徒手", "time": "晚上"})
    assert merged.goal == "减脂"
    assert merged.equipment == "徒手"
    assert merged.time == "晚上"
    assert merged.complete()


def test_slot_store_merge_and_get():
    store = SlotStore(ttl_seconds=60)
    merged = store.merge(1, "s1", {"goal": "增肌", "injuries": ["腰"]})
    assert merged.goal == "增肌"
    assert merged.injuries == ["腰"]
    fetched = store.get(1, "s1")
    assert fetched.goal == "增肌"


def test_extractor_rule_fallback():
    extractor = SlotExtractor(llm=DummyLLM(""))
    payload = extractor.extract("我想减脂，膝盖不好，家里徒手，晚上练")
    assert payload["goal"] == "减脂"
    assert payload["injuries"] == ["膝"]
    assert payload["equipment"] == "徒手"
    assert payload["time"] == "晚上"
    assert payload["location"] == "家里"


def test_validator_basic():
    validator = SlotValidator()
    result = validator.validate(SlotState(goal="康复", injuries=["腰"], equipment="徒手"))
    assert result.valid
    assert not result.errors


def test_clarifier_limits():
    clarifier = SlotClarifier(max_rounds=2)
    state = SlotState(goal=None, injuries=[])
    first = clarifier.decide(state)
    assert first.action == "clarify"
    state.clarifying_rounds = 3
    second = clarifier.decide(state)
    assert second.action == "fallback"
    assert second.should_fallback


def test_archiver_writes_only_delta():
    class MemoryStub:
        def __init__(self):
            self.items = []

        def upsert_long_term_memory(self, user_id, item, session_id=None):
            self.items.append((user_id, item, session_id))
            return item

    archiver = SlotArchiver(memory_store=MemoryStub())
    prev = SlotState(goal="减脂", injuries=["膝"], equipment="徒手")
    curr = SlotState(goal="减脂", injuries=["膝", "腰"], equipment="哑铃", time="晚上")
    result = archiver.archive(user_id=1, session_id="s1", previous=prev, current=curr)
    assert len(result.saved) == 3

