"""BodyPart 模型与关联测试"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import BodyPart, Exercise, exercise_body_parts
from app.repositories.fitness_repository import FitnessRepository


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_body_part_table_exists():
    """body_parts 与关联表应注册在 Base.metadata 上"""
    assert "body_parts" in Base.metadata.tables
    assert "exercise_body_parts" in Base.metadata.tables


def test_save_and_query_body_part(session):
    repo = FitnessRepository(session)
    bp_id = repo.save_body_part("膝关节", "下肢关键部位")
    assert repo.body_part_by_name("膝关节")["id"] == bp_id
    assert len(repo.body_parts()) == 1
    # 重复保存应为幂等（同 name 不重复建行）
    repo.save_body_part("膝关节")
    assert len(repo.body_parts()) == 1


def test_link_exercise_body_part(session):
    repo = FitnessRepository(session)
    bp_id = repo.save_body_part("膝关节")
    ex_id = repo.save_exercise({
        "name": "深蹲", "category": "力量训练", "difficulty": 2,
        "target": "下肢", "equipment": "徒手", "standard_json": "{}",
    })
    repo.link_exercise_body_part(ex_id, bp_id)
    session.flush()

    exercises = repo.exercises_for_body_part(bp_id)
    assert [e["name"] for e in exercises] == ["深蹲"]


def test_model_relationship(session):
    """ORM 层 Exercise ↔ BodyPart 多对多关系"""
    knee = BodyPart(name="膝关节")
    squat = Exercise(
        name="深蹲", category="力量训练", difficulty=2,
        target="下肢力量", equipment="徒手", standard_json="{}",
    )
    squat.body_parts.append(knee)
    session.add(squat)
    session.commit()

    fetched = session.query(Exercise).filter_by(name="深蹲").first()
    assert [b.name for b in fetched.body_parts] == ["膝关节"]
