from __future__ import annotations

import json
from contextlib import contextmanager

import agents
from agents import GameAgent, MotionAgent, ProfileAgent, RecommendAgent, ReportAgent
from app.agents.embedding_store import ExerciseVectorStore
from app.agents.output_parser import OutputParser


class DemoLLMClient:
    """Local deterministic LLM stand-in for agent debugging without API keys."""

    def invoke(self, prompt: str) -> str:
        if '"recommendations"' in prompt:
            return json.dumps({
                "recommendations": [
                    {"name": "平板支撑", "reason": "匹配核心稳定目标，且对膝盖冲击较低。", "score": 94},
                    {"name": "深蹲", "reason": "适合基础力量训练，但需要控制膝盖方向。", "score": 82},
                    {"name": "开合跳", "reason": "可提升心肺，但膝盖不适时应降低频率。", "score": 68},
                ]
            }, ensure_ascii=False)
        if '"title"' in prompt and '"analysis"' in prompt and '"plan"' in prompt:
            return json.dumps({
                "title": "本周训练总结",
                "summary": "近期训练整体稳定，核心类动作表现更好，深蹲需要继续控制动作质量。",
                "analysis": "平均分处于良好区间，薄弱点集中在下肢动作稳定性和膝盖方向控制。",
                "plan": ["优先安排核心稳定训练", "深蹲降速练习 2 组", "避免连续高冲击训练"],
            }, ensure_ascii=False)
        if '"evaluation"' in prompt:
            return json.dumps({
                "evaluation": {
                    "score": 86,
                    "mistakes": ["膝角控制基本稳定，但动作幅度略保守"],
                    "suggestions": ["下蹲时保持膝盖与脚尖同向", "放慢节奏并维持躯干稳定"],
                }
            }, ensure_ascii=False)
        if '"message"' in prompt and '"next_goal"' in prompt:
            return json.dumps({
                "message": "这次训练完成度不错，动作质量比单纯追求速度更重要。",
                "strategy": "继续用低冲击动作建立稳定反馈，每次只提高一个小指标。",
                "next_goal": "下次完成 20 分钟核心训练，并把动作评分稳定在 88 分以上。",
            }, ensure_ascii=False)
        return json.dumps({
            "profile": {
                "fitness_level": "初级偏进阶",
                "preference": "核心稳定和低冲击力量训练",
                "goal": "每周完成 3 次训练并逐步提升动作标准度",
                "risk": "膝盖不适时避免高冲击跳跃动作",
            }
        }, ensure_ascii=False)


class DemoGraph:
    def __init__(self):
        self.exercises = [
            {
                "name": "深蹲",
                "category": "力量训练",
                "difficulty": 1,
                "target": "下肢力量",
                "equipment": "徒手",
                "standard_json": "{}",
            },
            {
                "name": "平板支撑",
                "category": "核心训练",
                "difficulty": 1,
                "target": "核心稳定",
                "equipment": "瑜伽垫",
                "standard_json": "{}",
            },
            {
                "name": "开合跳",
                "category": "有氧训练",
                "difficulty": 1,
                "target": "心肺耐力",
                "equipment": "徒手",
                "standard_json": "{}",
            },
        ]

    def refresh(self):
        return None

    def recommend_exercises(self, user):
        return [
            {**item, "match_score": 72, "reason": "图谱候选：难度适合当前体能"}
            for item in self.exercises
        ]

    def recommend_venues(self, user, exercise_name=None):
        return [
            {
                "name": "校园健身中心",
                "address": "校园东区",
                "match_score": 90,
                "reason": "距离近，适合低冲击训练",
            }
        ]


class DemoRepo:
    def settle_points(self, user_id: int, score: int, duration: int) -> dict:
        return {"points": 28, "total_points": 148, "level": 2, "unlocked": ["森林探索关卡"]}


class FakeFitnessRepository:
    def __init__(self, session):
        self.session = session

    def recent_sessions(self, user_id: int, limit: int = 10) -> list[dict]:
        return demo_history()[:limit]


@contextmanager
def fake_session_scope():
    yield object()


def demo_user() -> dict:
    return {
        "id": 1,
        "nickname": "李同学",
        "age": 20,
        "fitness_level": "beginner",
        "preference": "核心训练 低冲击 力量训练",
        "injuries": "膝盖偶尔不适",
        "location": "校园东区",
    }


def demo_history() -> list[dict]:
    return [
        {"exercise_name": "平板支撑", "score": 90, "points": 30, "duration": 60, "created_at": "2026-07-18 10:00:00"},
        {"exercise_name": "深蹲", "score": 76, "points": 22, "duration": 50, "created_at": "2026-07-17 18:30:00"},
        {"exercise_name": "开合跳", "score": 82, "points": 24, "duration": 45, "created_at": "2026-07-16 19:00:00"},
    ]


def demo_pose() -> dict:
    return {
        "confidence": 92,
        "stability_score": 84,
        "knee_angle": 96,
        "hip_angle": 148,
        "shoulder_balance": 2.5,
        "raw_landmarks_json": "{}",
    }


def build_recommend_agent(llm_client: DemoLLMClient) -> RecommendAgent:
    agent = object.__new__(RecommendAgent)
    agent.llm_client = llm_client
    agent.output_parser = OutputParser()
    agent.graph = DemoGraph()
    agent.vector_store = ExerciseVectorStore()
    return agent


def print_section(title: str, payload):
    print(f"\n=== {title} ===")
    if isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main():
    llm = DemoLLMClient()
    user = demo_user()
    pose = demo_pose()

    profile_agent = ProfileAgent(llm_client=llm)
    recommend_agent = build_recommend_agent(llm)
    evaluate_agent = MotionAgent(llm_client=llm)
    motivation_agent = GameAgent(llm_client=llm)
    report_agent = ReportAgent(llm_client=llm)

    original_session_scope = agents.session_scope
    original_repository = agents.FitnessRepository
    agents.session_scope = fake_session_scope
    agents.FitnessRepository = FakeFitnessRepository
    try:
        print_section("Profile Agent 结果", profile_agent.summarize(user))
        print_section("Recommend Agent 结果", recommend_agent.recommend(user))
        print_section("Evaluate Agent 姿态特征", evaluate_agent.pose_features(pose, fallback_score=80))
        print_section("Evaluate Agent 结果", evaluate_agent.evaluate("深蹲", 80, pose))
        print_section("Motivation Agent 结果", motivation_agent.settle(DemoRepo(), user, 86, 60))
        print_section("Report Agent 结果", report_agent.build_report(user["id"]))
    finally:
        agents.session_scope = original_session_scope
        agents.FitnessRepository = original_repository


if __name__ == "__main__":
    main()
