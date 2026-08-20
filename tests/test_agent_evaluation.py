from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation import AgentRegressionRunner, EvaluationCase, LLMAsJudge, ManualReviewStore, load_cases
from app.evaluation.judge import JudgeResult, ReviewRecord
from tools.run_agent_regression import compare_reports, enforce


def test_load_agent_eval_cases_from_seed() -> None:
    cases = load_cases(Path("tools/data_seed/agent_eval_cases.json"))
    assert len(cases) == 7
    assert cases[0].question
    assert cases[0].expected_answer
    assert not any(case.manual_review for case in cases)


def test_llm_as_judge_heuristic_marks_low_risk_case_as_pass() -> None:
    case = EvaluationCase(
        id="case-1",
        entrypoint="chat",
        question="我是新手，一周练几次比较合适？",
        expected_answer="新手建议每周2到3次，隔天恢复，再根据状态逐步增加。",
        expected_citations=["新手", "一周三练"],
    )
    judge = LLMAsJudge(llm_client=None)
    result = judge.judge(
        case,
        actual_answer="新手建议每周2到3次，隔天恢复，再根据状态逐步增加。",
        citations=["[1] 新手"],
        sources=[{"title": "新手入门指南", "content": "一周三练"}],
        mode="fallback",
        latency_ms=800,
    )
    assert result.verdict == "pass"
    assert result.citation_hit_rate == 1.0
    assert result.relevance > 0.5
    assert result.manual_review is False


def test_manual_review_store_roundtrip(tmp_path: Path) -> None:
    store = ManualReviewStore(tmp_path / "manual_reviews.jsonl")
    store.append(ReviewRecord(case_id="case-1", reviewer="alice", decision="pass", notes="ok"))
    store.append(ReviewRecord(case_id="case-2", reviewer="bob", decision="fail", notes="needs work"))
    records = store.read_all()
    assert [record.case_id for record in records] == ["case-1", "case-2"]
    assert store.reviewed_case_ids() == {"case-1", "case-2"}


def test_agent_regression_runner_summarizes_quality_and_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.evaluation import runner as runner_module

    class DummyChatPipeline:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, question, **kwargs):
            return SimpleNamespace(
                answer="根据证据，先从低冲击开始训练。[1]",
                mode="online",
                fallback_reason="",
                citations=["[1]"],
                sources=[{"title": "低冲击训练", "content": "先从低冲击开始训练"}],
                retrieval_counts={"bm25": 1, "vector": 1, "graph": 0},
                rewrite_mode="online",
                rerank_mode="online",
            )

    class DummyProfileAgent:
        def __init__(self, *args, **kwargs):
            pass

        def summarize(self, user, **kwargs):
            return {
                "profile": "beginner 低冲击 膝盖偶尔不适",
                "mode": "online",
                "fallback_reason": "",
                "citations": ["[1]"],
                "sources": [{"title": "画像", "content": "beginner"}],
                "retrieval_counts": {"profile": 1},
            }

    class DummyRecommendAgent:
        def __init__(self, *args, **kwargs):
            pass

        def recommend(self, user, **kwargs):
            return {
                "recommendations": [{"name": "平板支撑", "score": 90}],
                "mode": "online",
                "fallback_reason": "",
                "citations": ["[1]"],
                "sources": [{"title": "推荐", "content": "平板支撑"}],
                "retrieval_counts": {"recommend": 1},
            }

    class DummyEvaluateAgent:
        def __init__(self, *args, **kwargs):
            pass

        def evaluate(self, exercise_name, raw_score, pose_data=None):
            return {
                "evaluation": {"score": 88, "mistakes": [], "suggestions": []},
                "mode": "online",
                "fallback_reason": "",
                "citations": ["[1]"],
                "sources": [{"title": "评估", "content": exercise_name}],
                "retrieval_counts": {"evaluate": 1},
            }

    class DummyMotivationAgent:
        def __init__(self, *args, **kwargs):
            pass

        def settle(self, user, score, duration, **kwargs):
            return {
                "motivation": "继续保持。",
                "mode": "online",
                "fallback_reason": "",
                "citations": ["[1]"],
                "sources": [{"title": "激励", "content": "继续保持"}],
                "retrieval_counts": {"motivation": 1},
            }

    class DummyReportAgent:
        def __init__(self, *args, **kwargs):
            pass

        def build_report(self, training_records, **kwargs):
            return {
                "summary": "两次训练 平均80 总时长45",
                "mode": "online",
                "fallback_reason": "",
                "citations": ["[1]"],
                "sources": [{"title": "报告", "content": "两次训练"}],
                "retrieval_counts": {"report": 1},
            }

    class FakeJudge:
        def judge(self, case, **kwargs):
            verdict = "review" if case.manual_review else "pass"
            return JudgeResult(
                relevance=0.91,
                citation_hit_rate=1.0,
                safety=1.0,
                overall=0.94 if verdict == "pass" else 0.7,
                confidence=0.9,
                verdict=verdict,
                feedback="ok",
                judge_mode="heuristic",
                manual_review=case.manual_review or verdict != "pass",
                raw={"case_id": case.id},
            )

    monkeypatch.setattr(runner_module, "FitnessKnowledgeBase", lambda: object())
    monkeypatch.setattr(runner_module, "HybridRAGPipeline", DummyChatPipeline)
    monkeypatch.setattr(runner_module, "ProfileAgent", DummyProfileAgent)
    monkeypatch.setattr(runner_module, "RecommendAgent", DummyRecommendAgent)
    monkeypatch.setattr(runner_module, "EvaluateAgent", DummyEvaluateAgent)
    monkeypatch.setattr(runner_module, "MotivationAgent", DummyMotivationAgent)
    monkeypatch.setattr(runner_module, "ReportAgent", DummyReportAgent)

    cases = [
        EvaluationCase(
            id="chat",
            entrypoint="chat",
            question="我的膝盖有点不适，想重新开始练，怎么安排？",
            expected_answer="先从低冲击、无痛范围开始，优先保护膝盖，必要时寻求专业评估。",
            expected_citations=["低冲击", "保护膝盖"],
        ),
        EvaluationCase(
            id="profile",
            entrypoint="profile",
            question="请总结一下我的训练画像",
            expected_answer="beginner 低冲击 膝盖偶尔不适",
        ),
        EvaluationCase(
            id="recommend",
            entrypoint="recommend",
            question="帮我推荐更适合膝盖不舒服的新手动作",
            expected_answer="平板支撑",
        ),
        EvaluationCase(
            id="evaluate",
            entrypoint="evaluate",
            question="帮我评估这个深蹲动作",
            expected_answer="补充完整且可见的 MediaPipe 关键点后再进行姿态纠错",
        ),
        EvaluationCase(
            id="motivation",
            entrypoint="motivation",
            question="给我一点鼓励",
            expected_answer="继续保持。",
        ),
        EvaluationCase(
            id="report",
            entrypoint="report",
            question="帮我生成本周训练报告",
            expected_answer="两次训练 平均80 总时长45",
            manual_review=True,
        ),
    ]

    runner = AgentRegressionRunner(cases, judge=FakeJudge())
    report = runner.run()

    assert report.case_count == 6
    assert report.pass_count == 5
    assert report.review_count == 1
    assert report.fail_count == 0
    assert report.degradation_count == 1
    assert report.citation_hit_rate == 1.0
    assert report.answer_relevance > 0.8
    assert report.manual_review_cases == ["report"]


def test_compare_and_enforce_thresholds() -> None:
    current = {
        "citation_hit_rate": 0.9,
        "answer_relevance": 0.88,
        "safety_score": 1.0,
        "overall_score": 0.92,
        "degradation_count": 1,
    }
    baseline = {
        "citation_hit_rate": 0.7,
        "answer_relevance": 0.65,
        "safety_score": 0.9,
        "overall_score": 0.78,
        "degradation_count": 3,
    }
    compare = compare_reports(current, baseline)
    assert compare["answer_relevance"]["delta"] == 0.23
    assert compare["degradation_count"]["delta"] == -2
    assert enforce(current | {"fail_count": 0}, SimpleNamespace(min_overall=0.8, min_relevance=0.7, min_citation_hit=0.6)) == 0
    assert enforce(current | {"fail_count": 1}, SimpleNamespace(min_overall=0.8, min_relevance=0.7, min_citation_hit=0.6)) == 1
