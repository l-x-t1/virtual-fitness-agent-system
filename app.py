import json
import mimetypes
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agents import AgentCoordinator
from database import execute, get_row, init_db, list_rows
from tools.enrich_venue_names import enrich as enrich_venue_names


mimetypes.add_type("application/wasm", ".wasm")
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
HOST = "127.0.0.1"
PORT = 8765

coordinator = None


class FitnessHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.send_file(TEMPLATE_DIR / "index.html")
        if parsed.path.startswith("/static/"):
            return self.send_file(BASE_DIR / parsed.path.lstrip("/"))
        if parsed.path == "/api/dashboard":
            user = self.current_user(parsed.query)
            if not user:
                return self.json_response({"error": "请先登录"}, 401)
            self.apply_request_location(user, parsed.query)
            return self.json_response(coordinator.dashboard(user))
        if parsed.path == "/api/exercises":
            return self.json_response({"exercises": coordinator.exercises()})
        if parsed.path == "/api/venues":
            return self.json_response({"venues": coordinator.venues()})
        if parsed.path == "/api/venues/enrich":
            return self.enrich_venues(parsed.query)
        if parsed.path == "/api/admin/equipment":
            return self.admin_equipment()
        if parsed.path == "/api/admin/equipment-map":
            return self.admin_equipment_map()
        if parsed.path == "/api/admin/knowledge-graph":
            return self.admin_knowledge_graph()
        if parsed.path == "/api/admin/overview":
            return self.admin_overview()
        if parsed.path == "/api/admin/users":
            return self.admin_users()
        if parsed.path == "/api/admin/user":
            return self.admin_user_detail(parsed.query)
        if parsed.path == "/api/admin/venues":
            return self.admin_venues(parsed.query)
        if parsed.path == "/api/admin/logs":
            return self.admin_logs()
        if parsed.path == "/api/admin/settings":
            return self.admin_settings()
        if parsed.path == "/api/admin/roles":
            return self.admin_roles()
        if parsed.path == "/api/sessions":
            user = self.current_user(parsed.query)
            if not user:
                return self.json_response({"error": "请先登录"}, 401)
            return self.json_response({"sessions": coordinator.sessions(user["id"])})
        if parsed.path == "/api/badges":
            user = self.current_user(parsed.query)
            if not user:
                return self.json_response({"error": "请先登录"}, 401)
            return self.json_response({"badges": coordinator.badges(user["id"])})
        if parsed.path == "/api/points/logs":
            user = self.current_user(parsed.query)
            if not user:
                return self.json_response({"error": "请先登录"}, 401)
            return self.json_response({"point_logs": coordinator.point_logs(user["id"])})
        return self.json_response({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self.read_json()
        if parsed.path == "/api/register":
            return self.register(body)
        if parsed.path == "/api/login":
            return self.login(body)
        if parsed.path == "/api/profile":
            return self.update_profile(body)
        if parsed.path == "/api/session":
            return self.submit_session(body)
        if parsed.path == "/api/pose/record":
            return self.save_pose_record(body)
        if parsed.path == "/api/admin/equipment":
            return self.save_equipment(body)
        if parsed.path == "/api/admin/equipment/delete":
            return self.delete_equipment(body)
        if parsed.path == "/api/admin/knowledge-graph":
            return self.save_knowledge_edge(body)
        if parsed.path == "/api/admin/knowledge-graph/delete":
            return self.delete_knowledge_edge(body)
        if parsed.path == "/api/admin/user":
            return self.save_admin_user(body)
        if parsed.path == "/api/admin/user/delete":
            return self.delete_admin_user(body)
        if parsed.path == "/api/admin/venue":
            return self.save_admin_venue(body)
        if parsed.path == "/api/admin/venue/delete":
            return self.delete_admin_venue(body)
        if parsed.path == "/api/admin/logs":
            return self.save_admin_log(body)
        if parsed.path == "/api/admin/announcement":
            return self.save_announcement(body)
        if parsed.path == "/api/admin/settings":
            return self.save_admin_settings(body)
        if parsed.path == "/api/admin/exercise":
            return self.save_admin_exercise(body)
        if parsed.path == "/api/admin/role":
            return self.save_admin_role(body)
        return self.json_response({"error": "Not found"}, 404)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def current_user(self, query):
        params = parse_qs(query)
        user_id = params.get("user_id", [None])[0]
        if not user_id:
            return None
        return get_row("SELECT * FROM users WHERE id = ?", (user_id,))

    def apply_request_location(self, user, query):
        params = parse_qs(query)
        try:
            if params.get("lat") and params.get("lon"):
                user["current_lat"] = float(params["lat"][0])
                user["current_lon"] = float(params["lon"][0])
                user["location"] = params.get("location", ["浏览器当前位置"])[0]
        except (TypeError, ValueError):
            pass

    def current_admin(self, query=None, body=None):
        user_id = None
        if query is not None:
            params = parse_qs(query)
            user_id = params.get("admin_user_id", params.get("user_id", [None]))[0]
        if body is not None:
            user_id = body.get("admin_user_id") or body.get("user_id")
        if not user_id:
            return None
        user = get_row("SELECT * FROM users WHERE id = ?", (user_id,))
        return user if user and user.get("role") == "admin" else None

    def register(self, body):
        required = ["username", "password", "nickname"]
        if any(not body.get(k) for k in required):
            return self.json_response({"error": "请填写用户名、密码和昵称"}, 400)
        try:
            user_id = execute(
                "INSERT INTO users(username, password, nickname) VALUES (?, ?, ?)",
                (body["username"].strip(), body["password"], body["nickname"].strip()),
            )
        except Exception:
            return self.json_response({"error": "用户名已存在"}, 409)
        user = get_row("SELECT * FROM users WHERE id = ?", (user_id,))
        return self.json_response({"user": user})

    def login(self, body):
        user = get_row(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (body.get("username", "").strip(), body.get("password", "")),
        )
        if not user:
            return self.json_response({"error": "用户名或密码错误"}, 401)
        return self.json_response({"user": user})

    def update_profile(self, body):
        user_id = body.get("user_id")
        if not user_id:
            return self.json_response({"error": "缺少用户 ID"}, 400)
        execute(
            """
            UPDATE users
            SET age = ?, fitness_level = ?, injuries = ?, preference = ?, location = ?
            WHERE id = ?
            """,
            (
                int(body.get("age", 20)),
                body.get("fitness_level", "beginner"),
                body.get("injuries", ""),
                body.get("preference", "综合训练"),
                body.get("location", "校园东区"),
                user_id,
            ),
        )
        user = get_row("SELECT * FROM users WHERE id = ?", (user_id,))
        return self.json_response({"user": user, "dashboard": coordinator.dashboard(user)})

    def submit_session(self, body):
        user_id = body.get("user_id")
        if not user_id:
            return self.json_response({"error": "请先登录"}, 401)
        result = coordinator.submit_session(
            int(user_id),
            body.get("exercise_name", "深蹲"),
            int(body.get("score", 75)),
            int(body.get("duration", 60)),
        )
        return self.json_response(result)

    def save_pose_record(self, body):
        if not body.get("user_id"):
            return self.json_response({"error": "缺少用户 ID"}, 400)
        record_id = coordinator.save_pose_record(body)
        return self.json_response({"id": record_id, "message": "姿态识别记录已保存"})

    def admin_equipment(self):
        if not self.current_admin(urlparse(self.path).query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        rows = list_rows(
            """
            SELECT e.*, v.name AS venue_name
            FROM fitness_equipment e
            LEFT JOIN venues v ON e.venue_id = v.id
            ORDER BY e.updated_at DESC, e.id DESC
            """
        )
        return self.json_response({"equipment": rows})

    def enrich_venues(self, query):
        if not self.current_admin(query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        params = parse_qs(query)
        try:
            lat = float(params.get("lat", [38.047])[0])
            lon = float(params.get("lon", [114.514])[0])
            radius_km = min(25, max(3, float(params.get("radius_km", [15])[0])))
        except (TypeError, ValueError):
            return self.json_response({"error": "缺少有效定位坐标"}, 400)
        try:
            venue_count, feature_count, update_count = enrich_venue_names(lat, lon, radius_km, 500)
            coordinator.recommendation.graph.refresh()
            return self.json_response({
                "checked": venue_count,
                "online_features": feature_count,
                "updated": update_count,
            })
        except Exception as exc:
            return self.json_response({"error": f"在线名称补全失败：{exc}"}, 502)

    def admin_equipment_map(self):
        query = urlparse(self.path).query
        admin = self.current_admin(query)
        if not admin:
            return self.json_response({"error": "需要管理员权限"}, 403)
        self.apply_request_location(admin, query)
        equipment = list_rows(
            """
            SELECT e.*, v.name AS venue_name
            FROM fitness_equipment e
            LEFT JOIN venues v ON e.venue_id = v.id
            ORDER BY e.crowd_index DESC, e.daily_uses DESC
            """
        )
        stats = get_row(
            """
            SELECT
                COUNT(*) AS total_count,
                SUM(CASE WHEN is_smart = 1 THEN 1 ELSE 0 END) AS smart_count,
                ROUND(AVG(crowd_index), 1) AS average_crowd,
                SUM(CASE WHEN crowd_index >= 70 THEN 1 ELSE 0 END) AS high_density_count,
                SUM(daily_uses) AS daily_uses
            FROM fitness_equipment
            """
        ) or {}
        categories = list_rows(
            """
            SELECT category, COUNT(*) AS count, ROUND(AVG(crowd_index), 1) AS average_crowd
            FROM fitness_equipment
            GROUP BY category
            ORDER BY count DESC
            """
        )
        venues = coordinator.recommendation.graph.recommend_venues(admin)
        return self.json_response({
            "equipment": equipment,
            "venues": venues,
            "stats": stats,
            "categories": categories,
        })

    def admin_venues(self, query):
        if not self.current_admin(query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        venues = list_rows(
            """
            SELECT id, name, display_name, location, resolved_address, latitude, longitude,
                   sport_type, leisure_type, kind, equipment, capacity, crowd_index,
                   air_quality, open_hours, rating, facility_count, density_score
            FROM venues
            ORDER BY id DESC
            LIMIT 200
            """
        )
        return self.json_response({"venues": venues})

    def admin_knowledge_graph(self):
        if not self.current_admin(urlparse(self.path).query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        graph = self.scientific_knowledge_graph()
        nodes = {node["id"]: node for node in graph["nodes"]}
        edges = list(graph["edges"])
        manual_edges = list_rows("SELECT * FROM knowledge_graph_edges ORDER BY id DESC LIMIT 80")
        for edge in manual_edges:
            edge = dict(edge)
            source_key = self.kg_node_key(edge["source_type"], edge.get("source_id"), edge["source_name"])
            target_key = self.kg_node_key(edge["target_type"], edge.get("target_id"), edge["target_name"])
            nodes.setdefault(source_key, {"id": source_key, "type": edge["source_type"], "name": edge["source_name"], "generated": False})
            nodes.setdefault(target_key, {"id": target_key, "type": edge["target_type"], "name": edge["target_name"], "generated": False})
            edge["source_key"] = source_key
            edge["target_key"] = target_key
            edge["generated"] = False
            edge["note"] = f"人工维护：{edge.get('note') or '补充关系'}"
            edges.append(edge)
        return self.json_response({
            "nodes": list(nodes.values()),
            "edges": edges,
            "meta": {
                "algorithm": "exercise-risk-equipment-venue-rule-graph",
                "source": "exercises, fitness_equipment, venues, knowledge_graph_edges",
            },
        })

    def scientific_knowledge_graph(self):
        exercises = list_rows("SELECT * FROM exercises ORDER BY difficulty, id LIMIT 40")
        equipment = list_rows(
            """
            SELECT e.*, v.name AS venue_name
            FROM fitness_equipment e
            LEFT JOIN venues v ON e.venue_id = v.id
            ORDER BY e.status <> 'normal' DESC, e.daily_uses DESC, e.id
            LIMIT 80
            """
        )
        venues = list_rows(
            """
            SELECT id, name, equipment, crowd_index, air_quality, density_score, capacity, kind, sport_type, leisure_type
            FROM venues
            ORDER BY crowd_index ASC, rating DESC, id DESC
            LIMIT 80
            """
        )
        nodes = {}
        edges = []

        def add_node(node_type, name, node_id=None):
            key = self.kg_node_key(node_type, node_id, name)
            nodes.setdefault(key, {"id": key, "type": node_type, "name": name, "source_id": node_id, "generated": True})
            return nodes[key]

        def add_edge(source, relation, target, weight, note):
            edge_id = f"gen:{source['id']}:{relation}:{target['id']}"
            edges.append({
                "id": edge_id,
                "source_type": source["type"],
                "source_id": source.get("source_id"),
                "source_name": source["name"],
                "source_key": source["id"],
                "relation_type": relation,
                "target_type": target["type"],
                "target_id": target.get("source_id"),
                "target_name": target["name"],
                "target_key": target["id"],
                "weight": round(max(0.05, min(float(weight), 1.0)), 2),
                "note": note,
                "generated": True,
            })

        groups = {
            "beginner": add_node("group", "新手人群"),
            "adult": add_node("group", "成年人群"),
            "senior": add_node("group", "中老年人群"),
            "knee_risk": add_node("group", "膝部风险人群"),
            "cardio": add_node("group", "心肺提升人群"),
        }
        maintenance_node = add_node("maintenance", "巡检维护")
        exercise_nodes = []

        for exercise in exercises:
            exercise_node = add_node("exercise", exercise["name"], exercise["id"])
            exercise_nodes.append((exercise, exercise_node))
            targets = self.kg_split_tags(exercise.get("target")) or ["全身"]
            for target in targets[:3]:
                body_part = add_node("body_part", target)
                add_edge(exercise_node, "训练目标", body_part, 0.82, f"{exercise['name']} 的主要训练目标包含 {target}。")

            difficulty = int(exercise.get("difficulty") or 2)
            low_impact = self.kg_is_low_impact_exercise(exercise)
            knee_risk = self.kg_has_knee_load(exercise)
            category = exercise.get("category") or ""
            name = exercise.get("name") or ""
            if difficulty <= 2:
                add_edge(groups["beginner"], "适合", exercise_node, 0.84 if low_impact else 0.68, "新手优先选择低到中等难度动作，并控制节奏。")
            add_edge(groups["adult"], "适合", exercise_node, 0.74 + (0.06 if difficulty <= 3 else -0.08), "成年人可按体能水平进行有氧与力量组合训练。")
            if low_impact and difficulty <= 2:
                add_edge(groups["senior"], "适合", exercise_node, 0.86, "中老年人群优先匹配低冲击、低到中等强度动作。")
            if not knee_risk and difficulty <= 2:
                add_edge(groups["knee_risk"], "适合", exercise_node, 0.78, "膝部风险人群优先选择低冲击、少跳跃动作。")
            if "有氧" in category or any(token in name for token in ("快走", "慢跑", "骑行", "游泳", "椭圆机", "开合跳")):
                add_edge(groups["cardio"], "适合", exercise_node, 0.84, "心肺提升目标需要规律有氧训练，并结合个人强度控制。")

            for requirement in self.kg_split_tags(exercise.get("equipment"))[:3]:
                if requirement and requirement not in {"无", "无需"}:
                    equipment_requirement = add_node("equipment", requirement)
                    add_edge(exercise_node, "需要器材", equipment_requirement, 0.76, f"{exercise['name']} 可使用 {requirement} 完成或辅助训练。")

        venue_by_id = {venue["id"]: venue for venue in venues}
        for item in equipment:
            equipment_node = add_node("equipment", item["name"], item["id"])
            category = item.get("category") or ""
            for exercise, exercise_node in exercise_nodes:
                score = self.kg_equipment_support_score(item, exercise)
                if score >= 0.62:
                    add_edge(equipment_node, "支持动作", exercise_node, score, f"{item['name']} 的类型/描述与 {exercise['name']} 的训练需求匹配。")
            venue = venue_by_id.get(item.get("venue_id"))
            if venue:
                venue_node = add_node("venue", venue["name"], venue["id"])
                add_edge(equipment_node, "部署于", venue_node, 1.0, f"{item['name']} 当前部署在 {venue['name']}。")
            daily_uses = int(item.get("daily_uses") or 0)
            crowd_index = int(item.get("crowd_index") or 0)
            if item.get("status") != "normal" or daily_uses >= 100 or crowd_index >= 65:
                weight = 0.52 + min(daily_uses / 420, 0.24) + min(crowd_index / 520, 0.14)
                if item.get("status") != "normal":
                    weight += 0.18
                add_edge(equipment_node, "巡检建议", maintenance_node, weight, f"状态 {item.get('status')}，日使用 {daily_uses} 次，人流指数 {crowd_index}。")

        for venue in venues[:18]:
            venue_node = add_node("venue", venue["name"], venue["id"])
            crowd_index = int(venue.get("crowd_index") or 0)
            air_quality = int(venue.get("air_quality") or 0)
            if crowd_index <= 55 and air_quality <= 80:
                add_edge(groups["adult"], "环境适配", venue_node, 0.82, "低到中等人流且空气质量较好，适合作为训练场馆。")
            if crowd_index <= 40:
                add_edge(groups["beginner"], "环境适配", venue_node, 0.78, "人流较低，新手更容易完成安全训练和动作学习。")

        unique_edges = {}
        for edge in edges:
            key = (edge["source_key"], edge["relation_type"], edge["target_key"])
            if key not in unique_edges or edge["weight"] > unique_edges[key]["weight"]:
                unique_edges[key] = edge
        return {
            "nodes": list(nodes.values()),
            "edges": sorted(unique_edges.values(), key=lambda item: (item["generated"], item["weight"]), reverse=True)[:120],
        }

    def kg_node_key(self, node_type, node_id, name):
        return f"{node_type}:{node_id or name}"

    def kg_split_tags(self, value):
        text = str(value or "").replace("，", ",").replace("、", ",").replace("/", ",").replace("；", ",")
        return [item.strip() for item in text.split(",") if item.strip()]

    def kg_is_low_impact_exercise(self, exercise):
        text = f"{exercise.get('name') or ''}{exercise.get('category') or ''}{exercise.get('target') or ''}"
        high_impact = any(token in text for token in ("跳", "冲刺", "深蹲", "弓步", "跑"))
        low_impact = any(token in text for token in ("快走", "漫步", "拉伸", "瑜伽", "游泳", "椭圆", "康复", "柔韧"))
        return low_impact or not high_impact

    def kg_has_knee_load(self, exercise):
        text = f"{exercise.get('name') or ''}{exercise.get('category') or ''}{exercise.get('target') or ''}"
        return any(token in text for token in ("深蹲", "弓步", "跳", "跑", "下肢"))

    def kg_equipment_support_score(self, equipment, exercise):
        equipment_text = f"{equipment.get('name') or ''}{equipment.get('category') or ''}{equipment.get('description') or ''}"
        exercise_text = f"{exercise.get('name') or ''}{exercise.get('category') or ''}{exercise.get('target') or ''}{exercise.get('equipment') or ''}"
        score = 0.0
        for token in self.kg_split_tags(equipment.get("category")) + self.kg_split_tags(equipment.get("name")):
            if token and token in exercise_text:
                score += 0.34
        if any(token in equipment_text for token in self.kg_split_tags(exercise.get("equipment"))):
            score += 0.42
        if "有氧" in equipment_text and any(token in exercise_text for token in ("有氧", "快走", "跑", "心肺")):
            score += 0.38
        if "力量" in equipment_text and any(token in exercise_text for token in ("力量", "深蹲", "下肢", "上肢")):
            score += 0.38
        if "综合" in equipment_text and any(token in exercise_text for token in ("综合", "全身", "协调")):
            score += 0.32
        return min(score, 0.95)

    def admin_overview(self):
        if not self.current_admin(urlparse(self.path).query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        today_stats = get_row(
            """
            SELECT
                (SELECT COUNT(*) FROM users WHERE role <> 'admin') AS total_users,
                (SELECT COUNT(DISTINCT user_id) FROM sessions WHERE DATE(created_at) = CURRENT_DATE) AS active_users,
                (SELECT COUNT(*) FROM sessions WHERE DATE(created_at) = CURRENT_DATE) AS total_sessions,
                (SELECT COALESCE(SUM(points), 0) FROM sessions WHERE DATE(created_at) = CURRENT_DATE) AS calories,
                (SELECT COUNT(*) FROM fitness_equipment WHERE status = 'normal') AS online_equipment,
                (SELECT COUNT(*) FROM fitness_equipment) AS total_equipment
            """
        ) or {}
        yesterday_stats = get_row(
            """
            SELECT
                (SELECT COUNT(DISTINCT user_id) FROM sessions WHERE DATE(created_at) = DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY)) AS active_users,
                (SELECT COUNT(*) FROM sessions WHERE DATE(created_at) = DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY)) AS total_sessions,
                (SELECT COALESCE(SUM(points), 0) FROM sessions WHERE DATE(created_at) = DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY)) AS calories
            """
        ) or {}
        active_users = list_rows(
            """
            SELECT
                u.id,
                u.username,
                u.nickname,
                u.points,
                u.preference,
                COUNT(s.id) AS session_count,
                COALESCE(ROUND(AVG(s.score), 1), 0) AS avg_score,
                MAX(s.created_at) AS last_train_at
            FROM users u
            LEFT JOIN sessions s
                ON s.user_id = u.id
                AND s.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            WHERE u.role <> 'admin'
            GROUP BY u.id, u.username, u.nickname, u.points, u.preference
            ORDER BY session_count DESC, u.points DESC, avg_score DESC, u.id DESC
            LIMIT 5
            """
        )
        recent_training = list_rows(
            """
            SELECT u.nickname, s.exercise_name, s.duration, s.points, s.created_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            ORDER BY s.created_at DESC
            LIMIT 8
            """
        )
        new_users_rows = list_rows(
            """
            SELECT DATE(created_at) AS day, COUNT(*) AS count
            FROM users
            WHERE role <> 'admin' AND created_at >= DATE_SUB(CURRENT_DATE, INTERVAL 6 DAY)
            GROUP BY DATE(created_at)
            """
        )
        active_rows = list_rows(
            """
            SELECT DATE(created_at) AS day, COUNT(DISTINCT user_id) AS count
            FROM sessions
            WHERE created_at >= DATE_SUB(CURRENT_DATE, INTERVAL 6 DAY)
            GROUP BY DATE(created_at)
            """
        )
        session_rows = list_rows(
            """
            SELECT DATE(created_at) AS day, COUNT(*) AS count
            FROM sessions
            WHERE created_at >= DATE_SUB(CURRENT_DATE, INTERVAL 6 DAY)
            GROUP BY DATE(created_at)
            """
        )
        training_type_rows = list_rows(
            """
            SELECT
                COALESCE(e.category, s.exercise_name, '其他训练') AS name,
                COUNT(*) AS value
            FROM sessions s
            LEFT JOIN exercises e ON e.name = s.exercise_name
            GROUP BY COALESCE(e.category, s.exercise_name, '其他训练')
            ORDER BY value DESC
            LIMIT 6
            """
        )
        operation_logs = list_rows(
            """
            SELECT action, detail, created_at
            FROM admin_operation_logs
            ORDER BY created_at DESC
            LIMIT 5
            """
        )
        announcements = list_rows(
            """
            SELECT title, content, level, published_at
            FROM system_announcements
            ORDER BY published_at DESC
            LIMIT 3
            """
        )
        high_density = get_row("SELECT COUNT(*) AS count FROM venues WHERE crowd_index >= 70") or {}
        maintenance = get_row("SELECT COUNT(*) AS count FROM fitness_equipment WHERE status <> 'normal'") or {}
        labels, new_users, trend_active_users, total_sessions = self.build_admin_trend(
            new_users_rows,
            active_rows,
            session_rows,
        )
        training_total = sum(int(row.get("value") or 0) for row in training_type_rows)
        training_types = [
            {
                "name": row["name"],
                "value": int(row.get("value") or 0),
                "percent": round((int(row.get("value") or 0) / training_total) * 100) if training_total else 0,
            }
            for row in training_type_rows
        ]
        return self.json_response({
            "kpis": [
                {"label": "注册用户总数", "value": self.format_count(today_stats.get("total_users")), "delta": "来自 users 表", "icon": "users"},
                {"label": "今日活跃用户", "value": self.format_count(today_stats.get("active_users")), "delta": self.percent_delta(today_stats.get("active_users"), yesterday_stats.get("active_users")), "icon": "pulse"},
                {"label": "今日训练次数", "value": self.format_count(today_stats.get("total_sessions")), "delta": self.percent_delta(today_stats.get("total_sessions"), yesterday_stats.get("total_sessions")), "icon": "dumbbell"},
                {"label": "设备在线数量", "value": self.format_count(today_stats.get("online_equipment")), "delta": self.online_equipment_label(today_stats), "icon": "device"},
                {"label": "卡路里消耗(今日)", "value": self.format_count(today_stats.get("calories")), "unit": "kcal", "delta": self.percent_delta(today_stats.get("calories"), yesterday_stats.get("calories")), "icon": "flame"},
            ],
            "active_ranking": [
                {
                    "rank": index + 1,
                    "nickname": row["nickname"],
                    "preference": row.get("preference") or "综合训练",
                    "active_index": self.active_index(row),
                    "points": row.get("points", 0),
                }
                for index, row in enumerate(active_users)
            ],
            "training_trend": {
                "labels": labels,
                "new_users": new_users,
                "active_users": trend_active_users,
                "total_sessions": total_sessions,
            },
            "training_types": training_types,
            "recent_training": recent_training,
            "operation_logs": operation_logs,
            "announcements": announcements,
            "notifications": self.build_admin_notifications(announcements, high_density, maintenance, today_stats),
        })

    def admin_users(self):
        if not self.current_admin(urlparse(self.path).query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        users = list_rows(
            """
            SELECT id, username, nickname, age, fitness_level, preference, location, points, level, role, created_at
            FROM users
            ORDER BY role DESC, points DESC, id DESC
            LIMIT 120
            """
        )
        role_stats = list_rows(
            """
            SELECT role, COUNT(*) AS count
            FROM users
            GROUP BY role
            ORDER BY count DESC
            """
        )
        segment_stats = get_row(
            """
            SELECT
                (SELECT COUNT(*) FROM users WHERE role <> 'admin') AS total_users,
                (SELECT COUNT(DISTINCT s.user_id)
                 FROM sessions s
                 JOIN users u ON u.id = s.user_id
                 WHERE u.role <> 'admin' AND s.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) AS active_users,
                (SELECT COUNT(*)
                 FROM users u
                 WHERE u.role <> 'admin'
                   AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.user_id = u.id)) AS new_users,
                (SELECT COUNT(*)
                 FROM users
                 WHERE role <> 'admin'
                   AND (fitness_level = 'beginner' OR COALESCE(injuries, '') <> '')) AS risk_users
            """
        ) or {}
        total_users = int(segment_stats.get("total_users") or 0)
        user_segments = [
            {
                "label": "高活跃用户",
                "detail": "近 7 天有训练记录，适合重点维护",
                "value": int(segment_stats.get("active_users") or 0),
                "total": total_users,
            },
            {
                "label": "新手用户",
                "detail": "尚未产生训练记录，需要引导完成首次训练",
                "value": int(segment_stats.get("new_users") or 0),
                "total": total_users,
            },
            {
                "label": "风险关注",
                "detail": "体能初级或有伤病标记，推荐低强度方案",
                "value": int(segment_stats.get("risk_users") or 0),
                "total": total_users,
            },
        ]
        return self.json_response({"users": users, "role_stats": role_stats, "user_segments": user_segments})

    def admin_user_detail(self, query):
        if not self.current_admin(query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        params = parse_qs(query)
        user_id = params.get("id", [None])[0]
        if not user_id:
            return self.json_response({"error": "缺少用户 ID"}, 400)
        user = get_row(
            """
            SELECT id, username, nickname, age, fitness_level, injuries, preference,
                   location, points, level, role, created_at
            FROM users
            WHERE id = ?
            """,
            (int(user_id),),
        )
        if not user:
            return self.json_response({"error": "账号不存在"}, 404)
        stats = get_row(
            """
            SELECT
                COUNT(*) AS session_count,
                COALESCE(ROUND(AVG(score), 1), 0) AS average_score,
                COALESCE(SUM(points), 0) AS earned_points,
                MAX(created_at) AS last_train_at
            FROM sessions
            WHERE user_id = ?
            """,
            (int(user_id),),
        ) or {}
        return self.json_response({"user": user, "stats": stats})

    def admin_logs(self):
        if not self.current_admin(urlparse(self.path).query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        logs = list_rows(
            """
            SELECT l.id, l.action, l.detail, l.created_at, u.nickname AS admin_name, u.username AS admin_username
            FROM admin_operation_logs l
            LEFT JOIN users u ON l.admin_user_id = u.id
            ORDER BY l.created_at DESC
            LIMIT 100
            """
        )
        audit_counts = get_row(
            """
            SELECT
                SUM(CASE WHEN action LIKE CONCAT(CHAR(37), '删除', CHAR(37)) THEN 1 ELSE 0 END) AS delete_count,
                SUM(CASE WHEN action LIKE CONCAT(CHAR(37), '权限', CHAR(37)) OR action LIKE CONCAT(CHAR(37), '角色', CHAR(37)) THEN 1 ELSE 0 END) AS permission_count,
                SUM(CASE WHEN action LIKE CONCAT(CHAR(37), '导出', CHAR(37)) OR action LIKE CONCAT(CHAR(37), '报表', CHAR(37)) THEN 1 ELSE 0 END) AS report_count
            FROM admin_operation_logs
            """
        ) or {}
        audit_rules = [
            {"label": "删除器材", "detail": "记录删除对象和管理员账号", "value": int(audit_counts.get("delete_count") or 0), "enabled": 1},
            {"label": "权限调整", "detail": "角色或权限变更需要二次确认", "value": int(audit_counts.get("permission_count") or 0), "enabled": 1},
            {"label": "报表导出", "detail": "保留导出时间和数据范围", "value": int(audit_counts.get("report_count") or 0), "enabled": 1},
        ]
        return self.json_response({"logs": logs, "audit_rules": audit_rules})

    def admin_settings(self):
        if not self.current_admin(urlparse(self.path).query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        self.ensure_admin_settings()
        rows = list_rows(
            """
            SELECT dict_key, dict_value, enabled
            FROM dictionaries
            WHERE dict_type = 'admin_setting'
            ORDER BY sort_order, id
            """
        )
        return self.json_response({"settings": [self.decorate_admin_setting(row) for row in rows]})

    def admin_setting_defaults(self):
        return {
            "pose_recognition": ("MediaPipe 识别", "体感训练默认启用姿态识别", 1),
            "venue_realtime": ("场馆实时更新", "定位变化后刷新周边场馆", 1),
            "training_reminder": ("训练提醒", "根据活跃状态推送个性化提醒", 1),
            "report_subscription": ("报表订阅", "生成日报和周报提醒", 1),
        }

    def ensure_admin_settings(self):
        defaults = self.admin_setting_defaults()
        for index, (key, (label, description, enabled)) in enumerate(defaults.items()):
            existing = get_row("SELECT id FROM dictionaries WHERE dict_type = ? AND dict_key = ?", ("admin_setting", key))
            if not existing:
                execute(
                    """
                    INSERT INTO dictionaries(dict_type, dict_key, dict_value, sort_order, enabled)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("admin_setting", key, f"{label}|{description}", index, enabled),
                )

    def decorate_admin_setting(self, row):
        defaults = self.admin_setting_defaults()
        fallback = defaults.get(row["dict_key"], (row["dict_key"], "后台配置项", 0))
        parts = str(row.get("dict_value") or "").split("|", 1)
        label = parts[0] if parts and parts[0] else fallback[0]
        description = parts[1] if len(parts) > 1 and parts[1] else fallback[1]
        return {
            "dict_key": row["dict_key"],
            "dict_value": row.get("dict_value"),
            "label": label,
            "description": description,
            "enabled": int(row.get("enabled") or 0),
        }

    def format_count(self, value):
        return f"{int(value or 0):,}"

    def percent_delta(self, current, previous):
        current = float(current or 0)
        previous = float(previous or 0)
        if previous <= 0:
            return "今日新增" if current > 0 else "暂无变化"
        delta = ((current - previous) / previous) * 100
        prefix = "+" if delta >= 0 else ""
        return f"{prefix}{delta:.1f}%"

    def online_equipment_label(self, stats):
        total = int(stats.get("total_equipment") or 0)
        online = int(stats.get("online_equipment") or 0)
        if not total:
            return "暂无器材"
        return f"在线率 {round((online / total) * 100)}%"

    def active_index(self, row):
        sessions = int(row.get("session_count") or 0)
        avg_score = float(row.get("avg_score") or 0)
        points = int(row.get("points") or 0)
        return min(100, round(sessions * 18 + avg_score * 0.45 + points / 40))

    def build_admin_trend(self, new_users_rows, active_rows, session_rows):
        start = date.today() - timedelta(days=6)
        days = [start + timedelta(days=offset) for offset in range(7)]

        def row_map(rows):
            return {str(row["day"]): int(row.get("count") or 0) for row in rows}

        new_map = row_map(new_users_rows)
        active_map = row_map(active_rows)
        session_map = row_map(session_rows)
        labels = [day.strftime("%m-%d") for day in days]
        keys = [day.isoformat() for day in days]
        return (
            labels,
            [new_map.get(key, 0) for key in keys],
            [active_map.get(key, 0) for key in keys],
            [session_map.get(key, 0) for key in keys],
        )

    def build_admin_notifications(self, announcements, high_density, maintenance, stats):
        notifications = [
            {
                "title": item.get("title") or "系统公告",
                "content": item.get("content") or "",
                "level": item.get("level") or "info",
                "created_at": item.get("published_at"),
            }
            for item in announcements[:2]
        ]
        dense_count = int(high_density.get("count") or 0)
        maintenance_count = int(maintenance.get("count") or 0)
        today_sessions = int(stats.get("total_sessions") or 0)
        if dense_count:
            notifications.append({"title": "密集区域提醒", "content": f"{dense_count} 个场馆当前处于高密度状态", "level": "warning"})
        if maintenance_count:
            notifications.append({"title": "器材维护提醒", "content": f"{maintenance_count} 台器材需要关注或维护", "level": "warning"})
        if today_sessions:
            notifications.append({"title": "今日训练更新", "content": f"今日已产生 {today_sessions} 条训练记录", "level": "success"})
        return notifications[:5]

    def admin_roles(self):
        if not self.current_admin(urlparse(self.path).query):
            return self.json_response({"error": "需要管理员权限"}, 403)
        defaults = [
            {"dict_key": "super_admin", "dict_value": "超级管理员|读写|读写|读写|读写|导出|配置", "enabled": 1},
            {"dict_key": "ops_admin", "dict_value": "运营管理员|读写|读写|读写|只读|导出|只读", "enabled": 1},
            {"dict_key": "device_admin", "dict_value": "设备管理员|只读|只读|只读|读写|导出|只读", "enabled": 1},
            {"dict_key": "auditor", "dict_value": "审计员|只读|只读|只读|只读|只读|审计", "enabled": 1},
        ]
        rows = list_rows(
            """
            SELECT dict_key, dict_value, enabled
            FROM dictionaries
            WHERE dict_type = 'admin_role'
            ORDER BY sort_order, id
            """
        )
        default_keys = {item["dict_key"] for item in defaults}
        custom_rows = [row for row in rows if row["dict_key"] not in default_keys]
        return self.json_response({"roles": [*defaults, *custom_rows]})


    def save_admin_user(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return self.json_response({"error": "需要管理员权限"}, 403)
        user_id = body.get("id")
        username = (body.get("username") or "").strip()
        nickname = (body.get("nickname") or "").strip() or username
        role = body.get("role") or "user"
        if not username:
            return self.json_response({"error": "请填写账号"}, 400)

        existing = get_row("SELECT id FROM users WHERE id = ?", (int(user_id),)) if user_id else get_row("SELECT id FROM users WHERE username = ?", (username,))
        username_owner = get_row("SELECT id FROM users WHERE username = ?", (username,))
        if username_owner and (not existing or int(username_owner["id"]) != int(existing["id"])):
            return self.json_response({"error": "用户名已存在"}, 409)

        age = int(body.get("age") or 30)
        fitness_level = body.get("fitness_level", "beginner")
        preference = body.get("preference", "综合训练")
        location = body.get("location", "石家庄市")

        if existing:
            fields = [
                "username = ?",
                "nickname = ?",
                "role = ?",
                "age = ?",
                "fitness_level = ?",
                "preference = ?",
                "location = ?",
            ]
            values = [username, nickname, role, age, fitness_level, preference, location]
            if body.get("password"):
                fields.append("password = ?")
                values.append(body.get("password"))
            values.append(existing["id"])
            execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", tuple(values))
            user_id = existing["id"]
        else:
            user_id = execute(
                """
                INSERT INTO users(username, password, nickname, age, fitness_level, preference, location, role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    body.get("password") or ("admin123" if role == "admin" else "123456"),
                    nickname,
                    age,
                    fitness_level,
                    preference,
                    location,
                    role,
                ),
            )
        self.record_admin_log(admin["id"], "保存后台账号", f"账号 {username} 已保存为 {role}")
        return self.json_response({
            "user": get_row(
                """
                SELECT id, username, nickname, role, age, fitness_level,
                       preference, location, points, level, created_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            )
        })

    def delete_admin_user(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return self.json_response({"error": "需要管理员权限"}, 403)
        user_id = body.get("id")
        if not user_id:
            return self.json_response({"error": "缺少用户 ID"}, 400)
        if int(user_id) == int(admin["id"]):
            return self.json_response({"error": "不能删除当前登录的管理员账号"}, 400)
        user = get_row("SELECT id, username, role FROM users WHERE id = ?", (int(user_id),))
        if not user:
            return self.json_response({"error": "账号不存在"}, 404)
        execute("DELETE FROM users WHERE id = ?", (int(user_id),))
        self.record_admin_log(admin["id"], "删除账号", f"账号 {user['username']} ({user['role']}) 已删除")
        return self.json_response({"message": "账号已删除"})

    def save_admin_log(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return self.json_response({"error": "需要管理员权限"}, 403)
        action = (body.get("action") or "后台操作").strip()
        detail = (body.get("detail") or "").strip()
        log_id = self.record_admin_log(admin["id"], action, detail)
        return self.json_response({"log": get_row("SELECT * FROM admin_operation_logs WHERE id = ?", (log_id,))})

    def save_announcement(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return self.json_response({"error": "需要管理员权限"}, 403)
        title = (body.get("title") or "").strip()
        content = (body.get("content") or "").strip()
        if not title or not content:
            return self.json_response({"error": "请填写公告标题和内容"}, 400)
        announcement_id = execute(
            """
            INSERT INTO system_announcements(title, content, level)
            VALUES (?, ?, ?)
            """,
            (title, content, body.get("level", "info")),
        )
        self.record_admin_log(admin["id"], "发布公告", title)
        return self.json_response({"announcement": get_row("SELECT * FROM system_announcements WHERE id = ?", (announcement_id,))})

    def save_admin_settings(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return self.json_response({"error": "需要管理员权限"}, 403)
        settings = body.get("settings") or {}
        defaults = self.admin_setting_defaults()
        saved = []
        for index, (key, value) in enumerate(settings.items()):
            label, description, _default_enabled = defaults.get(key, (key, "后台配置项", 0))
            dict_value = f"{label}|{description}"
            existing = get_row("SELECT id FROM dictionaries WHERE dict_type = ? AND dict_key = ?", ("admin_setting", key))
            enabled = 1 if value else 0
            if existing:
                execute(
                    "UPDATE dictionaries SET enabled = ?, dict_value = ?, sort_order = ? WHERE id = ?",
                    (enabled, dict_value, index, existing["id"]),
                )
            else:
                execute(
                    """
                    INSERT INTO dictionaries(dict_type, dict_key, dict_value, sort_order, enabled)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("admin_setting", key, dict_value, index, enabled),
                )
            saved.append({"dict_key": key, "label": label, "description": description, "enabled": enabled})
        self.record_admin_log(admin["id"], "保存系统设置", f"更新 {len(saved)} 项后台设置")
        return self.json_response({"settings": saved})

    def save_admin_exercise(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return self.json_response({"error": "需要管理员权限"}, 403)
        name = (body.get("name") or "").strip()
        category = (body.get("category") or "综合训练").strip()
        target = (body.get("target") or "全身协调").strip()
        equipment = (body.get("equipment") or "徒手").strip()
        if not name:
            return self.json_response({"error": "请填写课程名称"}, 400)
        difficulty = int(body.get("difficulty", 2))
        exercise_id = self.to_optional_int(body.get("id"))
        standard = {
            "duration": body.get("duration", "20分钟"),
            "target": target,
            "equipment": equipment,
            "created_by": "admin",
        }
        if exercise_id:
            existing = get_row("SELECT id FROM exercises WHERE id = ?", (exercise_id,))
            if not existing:
                return self.json_response({"error": "课程不存在"}, 404)
            duplicate = get_row("SELECT id FROM exercises WHERE name = ? AND id <> ?", (name, exercise_id))
            if duplicate:
                return self.json_response({"error": "课程名称已存在，请换一个名称"}, 409)
            execute(
                """
                UPDATE exercises
                SET name = ?, category = ?, difficulty = ?, target = ?, equipment = ?, standard_json = ?
                WHERE id = ?
                """,
                (name, category, difficulty, target, equipment, json.dumps(standard, ensure_ascii=False), exercise_id),
            )
        else:
            existing = get_row("SELECT id FROM exercises WHERE name = ?", (name,))
            if existing:
                exercise_id = existing["id"]
                execute(
                    """
                    UPDATE exercises
                    SET category = ?, difficulty = ?, target = ?, equipment = ?, standard_json = ?
                    WHERE id = ?
                    """,
                    (category, difficulty, target, equipment, json.dumps(standard, ensure_ascii=False), exercise_id),
                )
            else:
                exercise_id = execute(
                    """
                    INSERT INTO exercises(name, category, difficulty, target, equipment, standard_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (name, category, difficulty, target, equipment, json.dumps(standard, ensure_ascii=False)),
                )
        self.record_admin_log(admin["id"], "保存课程", f"课程 {name} 已写入 exercises 表")
        return self.json_response({"exercise": get_row("SELECT * FROM exercises WHERE id = ?", (exercise_id,))})

    def save_admin_role(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return self.json_response({"error": "需要管理员权限"}, 403)
        name = (body.get("name") or "").strip()
        key = (body.get("key") or name).strip().lower().replace(" ", "_")
        if not name:
            return self.json_response({"error": "请填写角色名称"}, 400)
        permissions = body.get("permissions") or {}
        value = "|".join([
            name,
            permissions.get("users", "只读"),
            permissions.get("training", "只读"),
            permissions.get("courses", "只读"),
            permissions.get("equipment", "只读"),
            permissions.get("reports", "只读"),
            permissions.get("system", "只读"),
        ])
        existing = get_row("SELECT id FROM dictionaries WHERE dict_type = ? AND dict_key = ?", ("admin_role", key))
        if existing:
            execute("UPDATE dictionaries SET dict_value = ?, enabled = 1 WHERE id = ?", (value, existing["id"]))
        else:
            execute(
                """
                INSERT INTO dictionaries(dict_type, dict_key, dict_value, sort_order, enabled)
                VALUES (?, ?, ?, ?, 1)
                """,
                ("admin_role", key, value, int(body.get("sort_order", 20))),
            )
        self.record_admin_log(admin["id"], "保存角色", f"角色 {name} 已写入 dictionaries 表")
        return self.json_response({"role": {"dict_key": key, "dict_value": value, "enabled": 1}})

    def save_equipment(self, body):
        if not self.current_admin(body=body):
            return self.json_response({"error": "需要管理员权限"}, 403)
        required = ["name", "category", "location", "latitude", "longitude"]
        if any(body.get(key) in (None, "") for key in required):
            return self.json_response({"error": "请填写器材名称、类型、位置和经纬度"}, 400)
        values = (
            body["name"].strip(),
            body["category"].strip(),
            self.to_optional_int(body.get("venue_id")),
            body["location"].strip(),
            float(body.get("latitude")),
            float(body.get("longitude")),
            1 if body.get("is_smart") else 0,
            body.get("status", "normal"),
            body.get("manufacturer", ""),
            int(body.get("crowd_index", 0)),
            int(body.get("daily_uses", 0)),
            body.get("last_maintenance") or None,
            body.get("description", ""),
        )
        if body.get("id"):
            equipment_id = int(body["id"])
            execute(
                """
                UPDATE fitness_equipment
                SET name = ?, category = ?, venue_id = ?, location = ?, latitude = ?, longitude = ?,
                    is_smart = ?, status = ?, manufacturer = ?, crowd_index = ?, daily_uses = ?,
                    last_maintenance = ?, description = ?
                WHERE id = ?
                """,
                (*values, equipment_id),
            )
        else:
            equipment_id = execute(
                """
                INSERT INTO fitness_equipment(
                    name, category, venue_id, location, latitude, longitude, is_smart,
                    status, manufacturer, crowd_index, daily_uses, last_maintenance, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        return self.json_response({"equipment": get_row("SELECT * FROM fitness_equipment WHERE id = ?", (equipment_id,))})

    def delete_equipment(self, body):
        if not self.current_admin(body=body):
            return self.json_response({"error": "需要管理员权限"}, 403)
        equipment_id = body.get("id")
        if not equipment_id:
            return self.json_response({"error": "缺少器材 ID"}, 400)
        execute("DELETE FROM fitness_equipment WHERE id = ?", (int(equipment_id),))
        return self.json_response({"message": "器材已删除"})

    def save_admin_venue(self, body):
        if not self.current_admin(body=body):
            return self.json_response({"error": "需要管理员权限"}, 403)
        required = ["name", "location", "latitude", "longitude", "equipment"]
        if any(body.get(key) in (None, "") for key in required):
            return self.json_response({"error": "请填写场馆名称、位置、经纬度和设施"}, 400)
        values = (
            body["name"].strip(),
            body.get("display_name") or body["name"].strip(),
            body["location"].strip(),
            body.get("resolved_address") or body["location"].strip(),
            float(body.get("latitude")),
            float(body.get("longitude")),
            body.get("sport_type", "fitness"),
            body.get("leisure_type", ""),
            body.get("kind", "indoor"),
            body["equipment"].strip(),
            int(body.get("capacity", 80)),
            int(body.get("crowd_index", 35)),
            int(body.get("air_quality", 60)),
            body.get("open_hours", "06:00-22:00"),
            float(body.get("rating", 4.6)),
            int(body.get("facility_count", 1)),
            float(body.get("density_score", body.get("crowd_index", 35))),
        )
        if body.get("id"):
            venue_id = int(body["id"])
            execute(
                """
                UPDATE venues
                SET name = ?, display_name = ?, location = ?, resolved_address = ?,
                    latitude = ?, longitude = ?, sport_type = ?, leisure_type = ?,
                    kind = ?, equipment = ?, capacity = ?, crowd_index = ?,
                    air_quality = ?, open_hours = ?, rating = ?, facility_count = ?,
                    density_score = ?
                WHERE id = ?
                """,
                (*values, venue_id),
            )
        else:
            venue_id = execute(
                """
                INSERT INTO venues(
                    name, display_name, location, resolved_address, latitude, longitude,
                    sport_type, leisure_type, kind, equipment, capacity, crowd_index,
                    air_quality, open_hours, rating, facility_count, density_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        return self.json_response({"venue": get_row("SELECT * FROM venues WHERE id = ?", (venue_id,))})

    def delete_admin_venue(self, body):
        if not self.current_admin(body=body):
            return self.json_response({"error": "需要管理员权限"}, 403)
        venue_id = body.get("id")
        if not venue_id:
            return self.json_response({"error": "缺少场馆 ID"}, 400)
        execute("DELETE FROM venues WHERE id = ?", (int(venue_id),))
        return self.json_response({"message": "场馆已删除"})

    def save_knowledge_edge(self, body):
        if not self.current_admin(body=body):
            return self.json_response({"error": "需要管理员权限"}, 403)
        required = ["source_type", "source_name", "relation_type", "target_type", "target_name"]
        if any(not body.get(key) for key in required):
            return self.json_response({"error": "请填写完整的知识图谱关系"}, 400)
        values = (
            body["source_type"].strip(),
            self.to_optional_int(body.get("source_id")),
            body["source_name"].strip(),
            body["relation_type"].strip(),
            body["target_type"].strip(),
            self.to_optional_int(body.get("target_id")),
            body["target_name"].strip(),
            float(body.get("weight", 1)),
            body.get("note", ""),
        )
        if body.get("id"):
            edge_id = int(body["id"])
            execute(
                """
                UPDATE knowledge_graph_edges
                SET source_type = ?, source_id = ?, source_name = ?, relation_type = ?,
                    target_type = ?, target_id = ?, target_name = ?, weight = ?, note = ?
                WHERE id = ?
                """,
                (*values, edge_id),
            )
        else:
            edge_id = execute(
                """
                INSERT INTO knowledge_graph_edges(
                    source_type, source_id, source_name, relation_type,
                    target_type, target_id, target_name, weight, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        return self.json_response({"edge": get_row("SELECT * FROM knowledge_graph_edges WHERE id = ?", (edge_id,))})

    def delete_knowledge_edge(self, body):
        if not self.current_admin(body=body):
            return self.json_response({"error": "需要管理员权限"}, 403)
        edge_id = body.get("id")
        if not edge_id:
            return self.json_response({"error": "缺少知识图谱关系 ID"}, 400)
        execute("DELETE FROM knowledge_graph_edges WHERE id = ?", (int(edge_id),))
        return self.json_response({"message": "关系已删除"})

    def record_admin_log(self, admin_user_id, action, detail=""):
        return execute(
            """
            INSERT INTO admin_operation_logs(admin_user_id, action, detail)
            VALUES (?, ?, ?)
            """,
            (admin_user_id, action, detail),
        )

    def to_optional_int(self, value):
        if value in (None, "", "null"):
            return None
        return int(value)

    def send_file(self, path):
        if not path.exists() or not path.is_file():
            return self.json_response({"error": "File not found"}, 404)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    global coordinator
    init_db()
    coordinator = AgentCoordinator()
    server = ThreadingHTTPServer((HOST, PORT), FitnessHandler)
    print(f"虚拟游戏化全民健身智能辅助系统已启动: http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
