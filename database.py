import os
import sqlite3
from pathlib import Path

import pymysql


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SQLITE_DB_PATH = DATA_DIR / "fitness.db"

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "123456"),
    "database": os.getenv("MYSQL_DATABASE", "virtual_fitness_agent_system"),
    "charset": "utf8mb4",
}


def _server_connect():
    config = MYSQL_CONFIG.copy()
    config.pop("database")
    return pymysql.connect(**config)


def _translate_sql(sql):
    return sql.replace("?", "%s")


class MySQLConnection:
    def __init__(self):
        self.conn = pymysql.connect(
            **MYSQL_CONFIG,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(_translate_sql(sql), params)
        return cur

    def executemany(self, sql, params):
        cur = self.conn.cursor()
        cur.executemany(_translate_sql(sql), params)
        return cur

    def commit(self):
        self.conn.commit()


def _ensure_database():
    with _server_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_CONFIG['database']}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()


def connect():
    _ensure_database()
    return MySQLConnection()


def init_db():
    _ensure_database()
    with connect() as conn:
        conn.execute("SET FOREIGN_KEY_CHECKS = 0")
        _create_tables(conn)
        _ensure_schema_updates(conn)
        conn.execute("SET FOREIGN_KEY_CHECKS = 1")
        _seed_from_sqlite(conn)


def _create_tables(conn):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT PRIMARY KEY AUTO_INCREMENT,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            nickname VARCHAR(100) NOT NULL,
            age INT DEFAULT 20,
            fitness_level VARCHAR(50) DEFAULT 'beginner',
            injuries TEXT,
            preference VARCHAR(255) DEFAULT '综合训练',
            location VARCHAR(255) DEFAULT '校园东区',
            points INT DEFAULT 0,
            level INT DEFAULT 1,
            role VARCHAR(50) DEFAULT 'user',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS exercises (
            id INT PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(100) UNIQUE NOT NULL,
            category VARCHAR(100) NOT NULL,
            difficulty INT NOT NULL,
            target VARCHAR(255) NOT NULL,
            equipment VARCHAR(255) NOT NULL,
            standard_json TEXT NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NOT NULL,
            height_cm DOUBLE,
            weight_kg DOUBLE,
            bmi DOUBLE,
            weekly_goal TEXT,
            risk_level VARCHAR(50) DEFAULT 'low',
            preferred_time VARCHAR(100),
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_user_profiles_user
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS exercise_standards (
            id INT PRIMARY KEY AUTO_INCREMENT,
            exercise_id INT NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            ideal_value DOUBLE,
            min_value DOUBLE,
            max_value DOUBLE,
            unit VARCHAR(50),
            risk_hint TEXT,
            CONSTRAINT fk_exercise_standards_exercise
                FOREIGN KEY(exercise_id) REFERENCES exercises(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS venues (
            id INT PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(100) UNIQUE NOT NULL,
            source_id VARCHAR(80),
            display_name VARCHAR(160),
            resolved_address VARCHAR(255),
            name_source VARCHAR(80),
            image_url VARCHAR(500),
            image_source VARCHAR(255),
            image_attribution VARCHAR(255),
            location VARCHAR(255) NOT NULL,
            latitude DOUBLE,
            longitude DOUBLE,
            leisure_type VARCHAR(80),
            sport_type VARCHAR(80),
            kind VARCHAR(50) DEFAULT 'outdoor',
            equipment VARCHAR(255) NOT NULL,
            capacity INT NOT NULL,
            crowd_index INT NOT NULL,
            air_quality INT NOT NULL,
            open_hours VARCHAR(100) NOT NULL,
            rating DOUBLE DEFAULT 4.6,
            facility_count INT DEFAULT 1,
            density_score DOUBLE DEFAULT 0,
            geometry_json MEDIUMTEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS fitness_equipment (
            id INT PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(120) NOT NULL,
            category VARCHAR(80) NOT NULL,
            venue_id INT,
            location VARCHAR(255) NOT NULL,
            latitude DOUBLE NOT NULL,
            longitude DOUBLE NOT NULL,
            is_smart TINYINT DEFAULT 0,
            status VARCHAR(50) DEFAULT 'normal',
            manufacturer VARCHAR(120),
            crowd_index INT DEFAULT 0,
            daily_uses INT DEFAULT 0,
            last_maintenance DATE,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT fk_equipment_venue
                FOREIGN KEY(venue_id) REFERENCES venues(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS knowledge_graph_edges (
            id INT PRIMARY KEY AUTO_INCREMENT,
            source_type VARCHAR(80) NOT NULL,
            source_id INT,
            source_name VARCHAR(160) NOT NULL,
            relation_type VARCHAR(80) NOT NULL,
            target_type VARCHAR(80) NOT NULL,
            target_id INT,
            target_name VARCHAR(160) NOT NULL,
            weight DOUBLE DEFAULT 1,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NOT NULL,
            exercise_name VARCHAR(100) NOT NULL,
            score INT NOT NULL,
            duration INT NOT NULL,
            points INT NOT NULL,
            feedback TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_sessions_user
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS pose_records (
            id INT PRIMARY KEY AUTO_INCREMENT,
            session_id INT,
            user_id INT NOT NULL,
            exercise_name VARCHAR(100) NOT NULL,
            confidence DOUBLE,
            stability_score DOUBLE,
            knee_angle DOUBLE,
            hip_angle DOUBLE,
            shoulder_balance DOUBLE,
            raw_landmarks_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_pose_records_session
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL,
            CONSTRAINT fk_pose_records_user
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS motion_metrics (
            id INT PRIMARY KEY AUTO_INCREMENT,
            session_id INT NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            metric_value DOUBLE NOT NULL,
            score INT,
            status VARCHAR(50),
            correction_advice TEXT,
            CONSTRAINT fk_motion_metrics_session
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS tips (
            id INT PRIMARY KEY AUTO_INCREMENT,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            tag VARCHAR(100) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS badges (
            id INT PRIMARY KEY AUTO_INCREMENT,
            name VARCHAR(100) UNIQUE NOT NULL,
            condition_text TEXT NOT NULL,
            icon VARCHAR(100) NOT NULL,
            reward_points INT DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS user_badges (
            id INT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NOT NULL,
            badge_id INT NOT NULL,
            earned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_user_badge(user_id, badge_id),
            CONSTRAINT fk_user_badges_user
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_user_badges_badge
                FOREIGN KEY(badge_id) REFERENCES badges(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS challenges (
            id INT PRIMARY KEY AUTO_INCREMENT,
            title VARCHAR(255) UNIQUE NOT NULL,
            exercise_name VARCHAR(100) NOT NULL,
            goal_text TEXT NOT NULL,
            difficulty INT NOT NULL,
            reward_points INT NOT NULL,
            scene VARCHAR(255) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_logs (
            id INT PRIMARY KEY AUTO_INCREMENT,
            user_id INT,
            agent_name VARCHAR(100) NOT NULL,
            action VARCHAR(255) NOT NULL,
            result TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_agent_logs_user
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS admin_operation_logs (
            id INT PRIMARY KEY AUTO_INCREMENT,
            admin_user_id INT,
            action VARCHAR(255) NOT NULL,
            detail TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_admin_operation_logs_user
                FOREIGN KEY(admin_user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS system_announcements (
            id INT PRIMARY KEY AUTO_INCREMENT,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            level VARCHAR(50) DEFAULT 'info',
            published_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS environment_snapshots (
            id INT PRIMARY KEY AUTO_INCREMENT,
            venue_id INT NOT NULL,
            crowd_index INT NOT NULL,
            air_quality INT NOT NULL,
            temperature DOUBLE NOT NULL,
            weather VARCHAR(100) NOT NULL,
            captured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_environment_venue
                FOREIGN KEY(venue_id) REFERENCES venues(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS recommendation_records (
            id INT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NOT NULL,
            recommendation_type VARCHAR(100) NOT NULL,
            target_id INT NOT NULL,
            target_name VARCHAR(255) NOT NULL,
            match_score DOUBLE NOT NULL,
            reason TEXT,
            agent_name VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_recommendation_records_user
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS challenge_records (
            id INT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NOT NULL,
            challenge_id INT NOT NULL,
            session_id INT,
            status VARCHAR(50) NOT NULL,
            score INT,
            combo_count INT DEFAULT 0,
            completed_at DATETIME,
            CONSTRAINT fk_challenge_records_user
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_challenge_records_challenge
                FOREIGN KEY(challenge_id) REFERENCES challenges(id) ON DELETE CASCADE,
            CONSTRAINT fk_challenge_records_session
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS point_logs (
            id INT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NOT NULL,
            source_type VARCHAR(100) NOT NULL,
            source_id INT,
            points_change INT NOT NULL,
            total_points INT NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_point_logs_user
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS levels (
            id INT PRIMARY KEY AUTO_INCREMENT,
            level INT UNIQUE NOT NULL,
            min_points INT NOT NULL,
            title VARCHAR(100) NOT NULL,
            unlock_text TEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NOT NULL,
            report_type VARCHAR(100) NOT NULL,
            session_count INT DEFAULT 0,
            average_score DOUBLE DEFAULT 0,
            weak_exercise VARCHAR(100),
            summary TEXT NOT NULL,
            suggestion TEXT,
            generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_reports_user
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dictionaries (
            id INT PRIMARY KEY AUTO_INCREMENT,
            dict_type VARCHAR(100) NOT NULL,
            dict_key VARCHAR(100) NOT NULL,
            dict_value VARCHAR(255) NOT NULL,
            sort_order INT DEFAULT 0,
            enabled TINYINT DEFAULT 1
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        "CREATE INDEX idx_users_username ON users(username)",
        "CREATE INDEX idx_user_profiles_user ON user_profiles(user_id)",
        "CREATE INDEX idx_sessions_user_time ON sessions(user_id, created_at DESC)",
        "CREATE INDEX idx_exercises_category ON exercises(category, difficulty)",
        "CREATE INDEX idx_exercise_standards_exercise ON exercise_standards(exercise_id)",
        "CREATE INDEX idx_pose_records_user_time ON pose_records(user_id, created_at DESC)",
        "CREATE INDEX idx_motion_metrics_session ON motion_metrics(session_id)",
        "CREATE INDEX idx_venues_location ON venues(location)",
        "CREATE UNIQUE INDEX uq_venues_source_id ON venues(source_id)",
        "CREATE INDEX idx_venues_geo ON venues(latitude, longitude)",
        "CREATE INDEX idx_venues_crowd_density ON venues(crowd_index, density_score)",
        "CREATE INDEX idx_equipment_venue ON fitness_equipment(venue_id, category)",
        "CREATE INDEX idx_equipment_geo ON fitness_equipment(latitude, longitude)",
        "CREATE INDEX idx_equipment_smart ON fitness_equipment(is_smart, status)",
        "CREATE INDEX idx_kg_source ON knowledge_graph_edges(source_type, source_id)",
        "CREATE INDEX idx_kg_target ON knowledge_graph_edges(target_type, target_id)",
        "CREATE INDEX idx_environment_venue_time ON environment_snapshots(venue_id, captured_at DESC)",
        "CREATE INDEX idx_recommendation_user_type ON recommendation_records(user_id, recommendation_type, created_at DESC)",
        "CREATE INDEX idx_challenge_records_user ON challenge_records(user_id, status)",
        "CREATE INDEX idx_user_badges_user ON user_badges(user_id)",
        "CREATE INDEX idx_point_logs_user_time ON point_logs(user_id, created_at DESC)",
        "CREATE INDEX idx_agent_logs_user_time ON agent_logs(user_id, created_at DESC)",
        "CREATE INDEX idx_admin_operation_logs_time ON admin_operation_logs(created_at DESC)",
        "CREATE INDEX idx_system_announcements_time ON system_announcements(published_at DESC)",
        "CREATE INDEX idx_reports_user_type ON reports(user_id, report_type, generated_at DESC)",
        "CREATE INDEX idx_dictionaries_type ON dictionaries(dict_type, sort_order)",
    ]
    for statement in statements:
        try:
            conn.execute(statement)
        except pymysql.err.OperationalError as exc:
            if exc.args[0] not in (1061, 1072):
                raise


def _ensure_schema_updates(conn):
    updates = [
        "ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'user'",
        "ALTER TABLE venues ADD COLUMN source_id VARCHAR(80)",
        "ALTER TABLE venues ADD COLUMN display_name VARCHAR(160)",
        "ALTER TABLE venues ADD COLUMN resolved_address VARCHAR(255)",
        "ALTER TABLE venues ADD COLUMN name_source VARCHAR(80)",
        "ALTER TABLE venues ADD COLUMN image_url VARCHAR(500)",
        "ALTER TABLE venues ADD COLUMN image_source VARCHAR(255)",
        "ALTER TABLE venues ADD COLUMN image_attribution VARCHAR(255)",
        "ALTER TABLE venues ADD COLUMN latitude DOUBLE",
        "ALTER TABLE venues ADD COLUMN longitude DOUBLE",
        "ALTER TABLE venues ADD COLUMN leisure_type VARCHAR(80)",
        "ALTER TABLE venues ADD COLUMN sport_type VARCHAR(80)",
        "ALTER TABLE venues ADD COLUMN kind VARCHAR(50) DEFAULT 'outdoor'",
        "ALTER TABLE venues ADD COLUMN rating DOUBLE DEFAULT 4.6",
        "ALTER TABLE venues ADD COLUMN facility_count INT DEFAULT 1",
        "ALTER TABLE venues ADD COLUMN density_score DOUBLE DEFAULT 0",
        "ALTER TABLE venues ADD COLUMN geometry_json MEDIUMTEXT",
        "CREATE UNIQUE INDEX uq_venues_source_id ON venues(source_id)",
        "CREATE INDEX idx_venues_geo ON venues(latitude, longitude)",
        "CREATE INDEX idx_venues_crowd_density ON venues(crowd_index, density_score)",
    ]
    for statement in updates:
        try:
            conn.execute(statement)
        except pymysql.err.OperationalError as exc:
            if exc.args[0] not in (1060, 1061):
                raise


def _seed_from_sqlite(conn):
    existing = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    if existing and existing["count"]:
        _ensure_demo_user(conn)
        _ensure_admin_demo_data(conn)
        return

    if SQLITE_DB_PATH.exists():
        _copy_sqlite_data(conn)
        _ensure_demo_user(conn)
        _ensure_admin_demo_data(conn)
        return

    _ensure_demo_user(conn)
    _ensure_admin_demo_data(conn)


def _ensure_demo_user(conn):
    demo = conn.execute("SELECT id, password, role FROM users WHERE username = ?", ("demo",)).fetchone()
    if demo:
        if demo["password"] != "123456":
            conn.execute("UPDATE users SET password = ? WHERE username = ?", ("123456", "demo"))
    else:
        conn.execute(
            """
            INSERT INTO users(username, password, nickname, age, fitness_level, preference, location, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("demo", "123456", "李同学", 20, "beginner", "综合训练", "校园东区", "user"),
        )

    admin = conn.execute("SELECT id, password, role FROM users WHERE username = ?", ("admin",)).fetchone()
    if admin:
        if admin["password"] != "admin123" or admin.get("role") != "admin":
            conn.execute("UPDATE users SET password = ?, role = ? WHERE username = ?", ("admin123", "admin", "admin"))
        return

    conn.execute(
        """
        INSERT INTO users(username, password, nickname, age, fitness_level, preference, location, role)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("admin", "admin123", "管理员", 30, "advanced", "综合管理", "管理中心", "admin"),
    )


def _ensure_admin_demo_data(conn):
    equipment_count = conn.execute("SELECT COUNT(*) AS count FROM fitness_equipment").fetchone()
    if not equipment_count or not equipment_count["count"]:
        venues = conn.execute("SELECT id, name, location FROM venues ORDER BY id LIMIT 6").fetchall()
        venue_map = {index + 1: venue for index, venue in enumerate(venues)}
        conn.executemany(
            """
            INSERT INTO fitness_equipment(
                name, category, venue_id, location, latitude, longitude, is_smart,
                status, manufacturer, crowd_index, daily_uses, last_maintenance, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("智能深蹲架 A1", "力量训练", venue_map.get(1, {}).get("id"), "河北体育馆力量区", 38.0427, 114.5149, 1, "normal", "FitFlow Lab", 68, 126, "2026-05-10", "支持姿态识别、次数统计和动作风险提醒。"),
                ("户外漫步机 B2", "有氧训练", venue_map.get(2, {}).get("id"), "裕彤国际体育中心东门", 38.0462, 114.5232, 0, "normal", "全民健身器材厂", 54, 88, "2026-04-28", "适合中老年低冲击有氧训练。"),
                ("智能划船器 C3", "综合训练", venue_map.get(3, {}).get("id"), "中山体育场体能区", 38.0344, 114.4683, 1, "maintenance", "FitFlow Lab", 41, 59, "2026-05-01", "采集心率、阻力档位和训练时长。"),
                ("双位太空漫步机 D4", "康复训练", venue_map.get(4, {}).get("id"), "石家庄全民健身中心广场", 38.0108, 114.5331, 0, "normal", "康体器械", 77, 143, "2026-05-12", "高频公共器材，适合轻量活动。"),
                ("智能引体向上架 E5", "力量训练", venue_map.get(5, {}).get("id"), "中央绿色体育公园北区", 38.0225, 114.4716, 1, "normal", "FitFlow Lab", 35, 47, "2026-05-08", "识别引体向上幅度、悬垂时间与完成质量。"),
            ],
        )

    edge_count = conn.execute("SELECT COUNT(*) AS count FROM knowledge_graph_edges").fetchone()
    if not edge_count or not edge_count["count"]:
        conn.executemany(
            """
            INSERT INTO knowledge_graph_edges(
                source_type, source_id, source_name, relation_type,
                target_type, target_id, target_name, weight, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("equipment", None, "智能深蹲架 A1", "supports", "exercise", None, "深蹲", 0.95, "器材可识别膝髋角度，适合力量训练纠错。"),
                ("equipment", None, "户外漫步机 B2", "suitable_for", "group", None, "中老年人群", 0.86, "低冲击有氧，风险较低。"),
                ("venue", None, "河北体育馆", "contains", "equipment", None, "智能深蹲架 A1", 1.0, "场馆-器材部署关系。"),
                ("equipment", None, "智能引体向上架 E5", "trains", "body_part", None, "背部与上肢", 0.9, "关联训练目标肌群。"),
                ("equipment", None, "智能划船器 C3", "requires", "maintenance", None, "传感器校准", 0.72, "维护状态影响推荐权重。"),
            ],
        )
    _ensure_admin_overview_demo_data(conn)


def _ensure_admin_overview_demo_data(conn):
    rank_users = [
        ("ff_rank_zhangsan", "张三", 98, "力量训练"),
        ("ff_rank_lisi", "李四", 94, "拳击训练"),
        ("ff_rank_wangwu", "王五", 89, "有氧训练"),
        ("ff_rank_zhaoliu", "赵六", 83, "体能训练"),
        ("ff_rank_sunqi", "孙七", 78, "体能训练"),
    ]
    for username, nickname, points, preference in rank_users:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE users
                SET nickname = ?, password = ?, age = ?, fitness_level = ?, preference = ?, location = ?, points = ?, level = ?, role = ?
                WHERE username = ?
                """,
                (nickname, "123456", 22, "advanced", preference, "石家庄市", points * 10, 5, "user", username),
            )
        else:
            conn.execute(
                """
                INSERT INTO users(username, password, nickname, age, fitness_level, preference, location, points, level, role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (username, "123456", nickname, 22, "advanced", preference, "石家庄市", points * 10, 5, "user"),
            )

    user_rows = conn.execute(
        """
        SELECT id, username, nickname
        FROM users
        WHERE username IN (?, ?, ?, ?, ?)
        """,
        tuple(item[0] for item in rank_users),
    ).fetchall()
    user_map = {row["username"]: row for row in user_rows}
    if user_map:
        existing_sessions = conn.execute(
            "SELECT COUNT(*) AS count FROM sessions WHERE user_id IN ({})".format(",".join(["?"] * len(user_map))),
            tuple(row["id"] for row in user_map.values()),
        ).fetchone()
        if not existing_sessions or not existing_sessions["count"]:
            session_rows = [
                ("ff_rank_zhangsan", "力量训练 - 初级", 92, 28, 320, "动作稳定，力量节奏达标。", "2026-05-18 15:38:00"),
                ("ff_rank_lisi", "拳击训练 - 中级", 88, 32, 410, "挥拳节奏稳定，核心控制良好。", "2026-05-18 15:33:00"),
                ("ff_rank_wangwu", "有氧训练 - 燃脂", 95, 45, 560, "心肺节奏保持优秀。", "2026-05-18 15:28:00"),
                ("ff_rank_zhaoliu", "体能训练 - 核心强化", 86, 25, 280, "核心稳定性提升明显。", "2026-05-18 15:22:00"),
                ("ff_rank_sunqi", "体能训练 - 核心强化", 84, 26, 260, "训练完成度良好。", "2026-05-18 15:18:00"),
                ("ff_rank_zhangsan", "力量训练 - 进阶", 90, 30, 340, "下肢力量表现稳定。", "2026-05-17 16:20:00"),
                ("ff_rank_lisi", "拳击训练 - 中级", 87, 30, 390, "出拳反应速度提升。", "2026-05-16 17:02:00"),
                ("ff_rank_wangwu", "有氧训练 - 燃脂", 93, 42, 520, "有氧连续性优秀。", "2026-05-15 18:10:00"),
            ]
            conn.executemany(
                """
                INSERT INTO sessions(user_id, exercise_name, score, duration, points, feedback, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (user_map[username]["id"], exercise, score, duration, points, feedback, created_at)
                    for username, exercise, score, duration, points, feedback, created_at in session_rows
                    if username in user_map
                ],
            )

    admin = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    admin_id = admin["id"] if admin else None
    log_count = conn.execute("SELECT COUNT(*) AS count FROM admin_operation_logs").fetchone()
    if not log_count or not log_count["count"]:
        conn.executemany(
            """
            INSERT INTO admin_operation_logs(admin_user_id, action, detail, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                (admin_id, "刷新数据", "管理员刷新运营总览与器材密度数据", "2026-05-18 15:40:00"),
                (admin_id, "导出报表", "导出今日训练与器材使用 CSV 报表", "2026-05-18 15:36:00"),
                (admin_id, "维护知识图谱", "新增智能深蹲架 A1 与深蹲动作关系", "2026-05-18 15:31:00"),
                (admin_id, "更新器材状态", "将智能划船器 C3 标记为维护中", "2026-05-18 15:24:00"),
                (admin_id, "发布公告", "发布晚高峰器材巡检提醒", "2026-05-18 15:18:00"),
            ],
        )

    announcement_count = conn.execute("SELECT COUNT(*) AS count FROM system_announcements").fetchone()
    if not announcement_count or not announcement_count["count"]:
        conn.executemany(
            """
            INSERT INTO system_announcements(title, content, level, published_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("晚高峰器材巡检提醒", "18:00-20:00 人群密集度预计升高，请优先巡检力量区和有氧区智能器材。", "warning", "2026-05-18 15:42:00"),
                ("知识图谱规则更新", "新增器材-动作-人群关系校验，推荐结果将优先考虑智能器材可用状态。", "info", "2026-05-18 14:20:00"),
                ("报表导出窗口", "今日运营报表已生成，可在管理员后台导出 CSV 文件用于归档。", "success", "2026-05-18 12:00:00"),
            ],
        )


def _copy_sqlite_data(conn):
    tables = [
        "users",
        "exercises",
        "venues",
        "sessions",
        "tips",
        "badges",
        "user_badges",
        "challenges",
        "agent_logs",
        "environment_snapshots",
    ]
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    try:
        conn.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in reversed(tables):
            conn.execute(f"DELETE FROM `{table}`")
        for table in tables:
            rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            columns = rows[0].keys()
            quoted_columns = ", ".join(f"`{column}`" for column in columns)
            placeholders = ", ".join(["?"] * len(columns))
            sql = f"INSERT INTO `{table}` ({quoted_columns}) VALUES ({placeholders})"
            conn.executemany(sql, [tuple(row[column] for column in columns) for row in rows])
        conn.execute("SET FOREIGN_KEY_CHECKS = 1")
    finally:
        sqlite_conn.close()


def row_to_dict(row):
    return dict(row) if row else None


def list_rows(sql, params=()):
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def get_row(sql, params=()):
    with connect() as conn:
        return row_to_dict(conn.execute(sql, params).fetchone())


def execute(sql, params=()):
    with connect() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
