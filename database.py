import json

from sqlalchemy import select

from app.db.base import Base
from app.db.models import Badge, Dictionary, Exercise, Level, Tip, User, Venue
from app.db.session import engine
from app.repositories import FitnessRepository, session_scope


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with session_scope() as session:
        repo = FitnessRepository(session)
        _ensure_users(repo)
        _ensure_catalog(session)


def _ensure_users(repo: FitnessRepository) -> None:
    if not repo.user_by_username("demo"):
        repo.create_user(
            "demo",
            "123456",
            "演示用户",
            age=20,
            fitness_level="beginner",
            preference="综合训练",
            location="校园东区",
            role="user",
        )
    if not repo.user_by_username("admin"):
        repo.create_user(
            "admin",
            "admin123",
            "管理员",
            age=30,
            fitness_level="advanced",
            preference="综合管理",
            location="管理中心",
            role="admin",
        )


def _ensure_catalog(session) -> None:
    if not session.scalar(select(Exercise.id).limit(1)):
        session.add_all([
            Exercise(name="深蹲", category="力量训练", difficulty=1, target="下肢力量", equipment="徒手", standard_json=json.dumps({"knee_angle": [70, 110]}, ensure_ascii=False)),
            Exercise(name="平板支撑", category="核心训练", difficulty=1, target="核心稳定", equipment="瑜伽垫", standard_json=json.dumps({"body_line": "straight"}, ensure_ascii=False)),
            Exercise(name="开合跳", category="有氧训练", difficulty=1, target="心肺耐力", equipment="徒手", standard_json=json.dumps({"landing": "soft"}, ensure_ascii=False)),
            Exercise(name="弓步蹲", category="力量训练", difficulty=2, target="下肢协调", equipment="徒手", standard_json=json.dumps({"knee_tracking": "toe"}, ensure_ascii=False)),
            Exercise(name="节奏冲刺", category="有氧训练", difficulty=3, target="爆发力", equipment="跑道", standard_json=json.dumps({"cadence": "stable"}, ensure_ascii=False)),
        ])

    if not session.scalar(select(Venue.id).limit(1)):
        session.add_all([
            Venue(name="河北体育馆", location="石家庄长安区", latitude=38.0427, longitude=114.5149, equipment="徒手,跑道,力量器械", capacity=120, crowd_index=35, air_quality=42, open_hours="06:00-22:00", rating=4.8, density_score=25),
            Venue(name="中山体育场", location="石家庄桥西区", latitude=38.0344, longitude=114.4683, equipment="跑道,瑜伽垫", capacity=80, crowd_index=42, air_quality=48, open_hours="06:30-21:30", rating=4.6, density_score=32),
            Venue(name="裕华全民健身中心", location="石家庄裕华区", latitude=38.0108, longitude=114.5331, equipment="力量器械,智能器材", capacity=100, crowd_index=58, air_quality=45, open_hours="08:00-22:00", rating=4.7, density_score=41),
        ])

    if not session.scalar(select(Badge.id).limit(1)):
        session.add_all([
            Badge(name="标准动作徽章", condition_text="单次训练评分达到 92 分", icon="award", reward_points=20),
            Badge(name="坚持训练徽章", condition_text="累计完成 7 次训练", icon="flame", reward_points=30),
        ])

    if not session.scalar(select(Tip.id).limit(1)):
        session.add_all([
            Tip(title="训练前热身", content="正式训练前进行 5 分钟动态热身。", tag="安全"),
            Tip(title="控制动作质量", content="分数低于 75 时优先降低速度。", tag="动作"),
        ])

    if not session.scalar(select(Level.id).limit(1)):
        session.add_all([
            Level(level=1, min_points=0, title="新手", unlock_text="基础训练"),
            Level(level=2, min_points=120, title="进阶", unlock_text="森林探索关卡"),
            Level(level=3, min_points=240, title="熟练", unlock_text="城市能量冲刺"),
        ])

    if not session.scalar(select(Dictionary.id).limit(1)):
        session.add_all([
            Dictionary(dict_type="admin_setting", dict_key="system_name", dict_value="虚拟游戏化全民健身智能辅助系统", sort_order=1, enabled=True),
            Dictionary(dict_type="admin_role", dict_key="admin", dict_value="管理员", sort_order=1, enabled=True),
            Dictionary(dict_type="admin_role", dict_key="user", dict_value="普通用户", sort_order=2, enabled=True),
        ])
