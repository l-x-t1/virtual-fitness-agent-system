"""Repository 层数据访问接口测试（补齐的 7 张表 + BodyPart）"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.repositories.fitness_repository import FitnessRepository


@pytest.fixture()
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield FitnessRepository(session)
    session.close()


def _seed_user(repo) -> int:
    return repo.create_user("demo", "123456", "演示用户")


def test_user_profile(repo):
    uid = _seed_user(repo)
    pid = repo.save_profile(uid, {"height_cm": 175, "weight_kg": 70, "risk_level": "medium"})
    assert pid > 0
    profile = repo.profile_by_user(uid)
    assert profile["height_cm"] == 175
    assert profile["risk_level"] == "medium"
    # 更新同一用户档案，应复用同一行
    repo.save_profile(uid, {"bmi": 22.8})
    assert repo.profile_by_user(uid)["bmi"] == 22.8


def test_exercise_standard(repo):
    ex_id = repo.save_exercise({
        "name": "深蹲", "category": "力量训练", "difficulty": 2,
        "target": "下肢", "equipment": "徒手", "standard_json": "{}",
    })
    std_id = repo.save_exercise_standard({
        "exercise_id": ex_id, "metric_name": "knee_angle",
        "min_value": 70, "max_value": 110, "unit": "deg", "risk_hint": "膝盖内扣",
    })
    assert std_id > 0
    standards = repo.exercise_standards(exercise_id=ex_id)
    assert standards[0]["metric_name"] == "knee_angle"
    assert standards[0]["risk_hint"] == "膝盖内扣"


def test_motion_metric(repo):
    uid = _seed_user(repo)
    sid = repo.add_session(uid, "深蹲", 85, 30, 10, "不错")
    mid = repo.save_motion_metric({
        "session_id": sid, "metric_name": "knee_angle",
        "metric_value": 92.5, "score": 90, "status": "ok",
    })
    assert mid > 0
    metrics = repo.motion_metrics(session_id=sid)
    assert metrics[0]["metric_name"] == "knee_angle"
    assert metrics[0]["metric_value"] == 92.5


def test_environment_snapshot(repo):
    vid = repo.save_venue({
        "name": "河北体育馆", "location": "石家庄长安区",
        "equipment": "跑道", "capacity": 100, "crowd_index": 35,
        "air_quality": 42, "open_hours": "06:00-22:00",
    })
    snap_id = repo.save_environment_snapshot({
        "venue_id": vid, "crowd_index": 40, "air_quality": 50,
        "temperature": 23.5, "weather": "多云",
    })
    assert snap_id > 0
    snaps = repo.environment_snapshots(venue_id=vid)
    assert snaps[0]["weather"] == "多云"
    assert snaps[0]["temperature"] == 23.5


def test_recommendation_record(repo):
    uid = _seed_user(repo)
    rid = repo.save_recommendation_record({
        "user_id": uid, "recommendation_type": "exercise", "target_id": 1,
        "target_name": "深蹲", "match_score": 88.5, "reason": "匹配目标",
    })
    assert rid > 0
    records = repo.recommendation_records(user_id=uid)
    assert records[0]["target_name"] == "深蹲"
    assert records[0]["match_score"] == 88.5


def test_challenge_and_record(repo):
    uid = _seed_user(repo)
    cid = repo.save_challenge({
        "title": "深蹲挑战", "exercise_name": "深蹲", "goal_text": "完成 10 次标准深蹲",
        "difficulty": 2, "reward_points": 20, "scene": "力量训练",
    })
    cr_id = repo.save_challenge_record({
        "user_id": uid, "challenge_id": cid, "status": "completed", "score": 90,
    })
    assert cr_id > 0
    records = repo.challenge_records(user_id=uid, status="completed")
    assert len(records) == 1
    assert records[0]["score"] == 90


def test_report(repo):
    uid = _seed_user(repo)
    rep_id = repo.save_report({
        "user_id": uid, "report_type": "weekly", "session_count": 3,
        "average_score": 85, "weak_exercise": "深蹲", "summary": "本周坚持训练",
    })
    assert rep_id > 0
    latest = repo.latest_report(uid)
    assert latest["summary"] == "本周坚持训练"
    assert len(repo.reports(user_id=uid)) == 1


def test_challenges_list(repo):
    repo.save_challenge({
        "title": "冲刺挑战", "exercise_name": "节奏冲刺", "goal_text": "保持节奏",
        "difficulty": 3, "reward_points": 30, "scene": "有氧",
    })
    assert len(repo.challenges()) == 1
