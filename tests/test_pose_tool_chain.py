from __future__ import annotations

import json
from pathlib import Path

from app.agents.evaluate_agent import EvaluateAgent
from app.llm.client import LLMConfigurationError
from app.services.training_service import TrainingService
from app.tools.pose_tool import PoseEvaluationTool
from app.models.training import PoseRecordSubmit


class OfflineLLM:
    def invoke(self, prompt):
        raise LLMConfigurationError("offline")

    async def ainvoke(self, prompt):
        raise LLMConfigurationError("offline")


def landmarks():
    points = [{"x": 0.0, "y": 0.0, "z": 0.0, "visibility": 0.0} for _ in range(33)]
    values = {
        11: (0.4, 0.2), 12: (0.6, 0.2),
        23: (0.45, 0.5), 24: (0.55, 0.5),
        25: (0.45, 0.7), 26: (0.55, 0.7),
        27: (0.45, 0.9), 28: (0.55, 0.9),
    }
    for index, (x, y) in values.items():
        points[index] = {"x": x, "y": y, "z": 0.0, "visibility": 0.99}
    return points


def test_complete_landmarks_generate_bilateral_motion_features_and_feedback():
    agent = EvaluateAgent(llm_client=OfflineLLM())
    result = PoseEvaluationTool(agent).evaluate_pose("深蹲", landmarks(), 82, 90, 78)
    features = result["data"]["motion_features"]
    evaluation = result["data"]["evaluation"]
    assert features["angle"]["left_knee"] is not None
    assert features["angle"]["right_knee"] is not None
    assert features["angle"]["left_hip"] is not None
    assert features["angle"]["right_hip"] is not None
    assert features["angle"]["shoulder_balance"] == 0
    assert features["confidence"] == 90
    assert {"score", "mistakes", "suggestions", "risk_level"} <= evaluation.keys()


def test_missing_landmarks_do_not_invent_joint_problems():
    agent = EvaluateAgent(llm_client=OfflineLLM())
    result = PoseEvaluationTool(agent).evaluate_pose("深蹲", [], 60)
    evaluation = result["data"]["evaluation"]
    assert result["fallback_reason"]
    assert evaluation["risk_level"] == "unknown"
    assert evaluation["mistakes"] == []
    assert not any("膝" in text or "髋" in text or "肩" in text for text in evaluation["mistakes"])


class Motion:
    def __init__(self):
        self.pose_data = None

    def evaluate_structured(self, exercise, score, pose_data):
        self.pose_data = pose_data
        return EvaluateAgent(llm_client=OfflineLLM()).evaluate(exercise, score, pose_data)


class Coordinator:
    def __init__(self):
        self.motion = Motion()
        self.saved = None

    def save_pose_record(self, data):
        self.saved = data
        return 88


def test_pose_record_service_connects_landmarks_to_agent_and_persistence():
    coordinator = Coordinator()
    result = TrainingService(coordinator).save_pose_record(7, {
        "exercise_name": "深蹲",
        "confidence": 90,
        "stability_score": 80,
        "raw_landmarks_json": "{}",
        "landmarks": landmarks(),
        "raw_score": 84,
    })
    raw = json.loads(coordinator.saved["raw_landmarks_json"])
    assert result["id"] == 88
    assert result["evaluation"]["score"] == 84
    assert result["motion_features"]["landmark_count"] == 33
    assert len(raw["landmarks"]) == 33
    assert coordinator.saved["knee_angle"] is not None


def test_keyboard_demo_without_landmarks_remains_safe():
    coordinator = Coordinator()
    result = TrainingService(coordinator).save_pose_record(7, {
        "exercise_name": "深蹲",
        "confidence": 0,
        "stability_score": 70,
        "raw_landmarks_json": '{"source":"keyboard","score":70}',
    })
    assert result["id"] == 88
    assert result["evaluation"]["risk_level"] != "high"
    assert coordinator.saved["knee_angle"] is None


def test_pose_request_model_accepts_legacy_and_landmark_payloads():
    legacy = PoseRecordSubmit(exercise_name="深蹲")
    current = PoseRecordSubmit(exercise_name="深蹲", landmarks=landmarks(), raw_score=80)
    assert legacy.landmarks is None
    assert legacy.raw_landmarks_json == "{}"
    assert len(current.landmarks) == 33


def test_browser_source_uploads_real_landmarks_and_displays_correction():
    source = Path("static/app.js").read_text(encoding="utf-8")
    assert "landmarks," in source
    assert "state.latestLandmarks.map" in source
    assert "姿态纠错" in source
