from urllib.parse import parse_qs, urlparse

from app.cache import cache_get_or_set
from app.cache import cache_keys
from app.core.security import hash_password
from app.repositories import FitnessRepository, session_scope

coordinator = None


class FitnessService:
    """Domain operations used by FastAPI controllers; data access is delegated to repositories."""

    def __init__(self, path: str = "", admin_user: dict | None = None):
        self.path = path
        self.admin_user = admin_user

    def current_user(self, query):
        user_id = parse_qs(query).get("user_id", [None])[0]
        if not user_id:
            return None
        with session_scope() as session:
            return FitnessRepository(session).user_by_id(int(user_id))

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
        if self.admin_user:
            return self.admin_user
        user_id = None
        if query is not None:
            params = parse_qs(query)
            user_id = params.get("admin_user_id", params.get("user_id", [None]))[0]
        if body is not None:
            user_id = body.get("admin_user_id") or body.get("user_id")
        if not user_id:
            return None
        with session_scope() as session:
            user = FitnessRepository(session).user_by_id(int(user_id))
        return user if user and user.get("role") == "admin" else None

    def update_profile(self, body):
        user_id = body.get("user_id")
        if not user_id:
            return {"error": "缺少用户 ID"}
        with session_scope() as session:
            user = FitnessRepository(session).update_profile(int(user_id), {
                "age": int(body.get("age", 20)),
                "fitness_level": body.get("fitness_level", "beginner"),
                "injuries": body.get("injuries", ""),
                "preference": body.get("preference", "综合训练"),
                "location": body.get("location", "校园东区"),
            })
        return {"user": user, "dashboard": coordinator.dashboard(user) if coordinator else {}}

    def enrich_venues(self, query):
        if not self.current_admin(query):
            return {"error": "需要管理员权限"}
        return {"checked": 0, "online_features": 0, "updated": 0, "message": "数据层已切换 ORM，在线补全请通过迁移脚本导入。"}

    def admin_equipment(self):
        with session_scope() as session:
            return {"equipment": FitnessRepository(session).equipment_with_venue()}

    def admin_equipment_map(self):
        return cache_get_or_set(cache_keys.EQUIPMENT_MAP, self._admin_equipment_map)

    def _admin_equipment_map(self):
        with session_scope() as session:
            repo = FitnessRepository(session)
            admin = self.current_admin(urlparse(self.path).query) or self.admin_user or {}
            self.apply_request_location(admin, urlparse(self.path).query)
            return {
                "equipment": repo.equipment_with_venue(order_by_usage=True),
                "venues": coordinator.recommendation.graph.recommend_venues(admin) if coordinator else repo.venues(),
                "stats": repo.equipment_stats(),
                "categories": repo.equipment_categories(),
            }

    def admin_venues(self, query):
        with session_scope() as session:
            return {"venues": FitnessRepository(session).venues(limit=200, admin_fields=True)}

    def admin_knowledge_graph(self):
        return cache_get_or_set(cache_keys.KNOWLEDGE_GRAPH, self._admin_knowledge_graph)

    def _admin_knowledge_graph(self):
        graph = self.scientific_knowledge_graph()
        nodes = {node["id"]: node for node in graph["nodes"]}
        edges = list(graph["edges"])
        with session_scope() as session:
            manual_edges = FitnessRepository(session).knowledge_edges(80)
        for edge in manual_edges:
            source_key = self.kg_node_key(edge["source_type"], edge.get("source_id"), edge["source_name"])
            target_key = self.kg_node_key(edge["target_type"], edge.get("target_id"), edge["target_name"])
            nodes.setdefault(source_key, {"id": source_key, "type": edge["source_type"], "name": edge["source_name"], "generated": False})
            nodes.setdefault(target_key, {"id": target_key, "type": edge["target_type"], "name": edge["target_name"], "generated": False})
            edges.append({**edge, "source_key": source_key, "target_key": target_key, "generated": False})
        return {"nodes": list(nodes.values()), "edges": edges, "meta": {"source": "ORM repositories"}}

    def scientific_knowledge_graph(self):
        with session_scope() as session:
            repo = FitnessRepository(session)
            exercises = repo.exercises(40)
            equipment = repo.equipment_with_venue(order_by_usage=True, limit=80)
            venues = repo.venues(80)
        nodes, edges = {}, []
        for exercise in exercises:
            key = self.kg_node_key("exercise", exercise["id"], exercise["name"])
            nodes[key] = {"id": key, "type": "exercise", "name": exercise["name"], "generated": True}
        for item in equipment:
            key = self.kg_node_key("equipment", item["id"], item["name"])
            nodes[key] = {"id": key, "type": "equipment", "name": item["name"], "generated": True}
            if item.get("venue_id"):
                target_key = self.kg_node_key("venue", item["venue_id"], item.get("venue_name") or "场馆")
                edges.append({"source_key": target_key, "target_key": key, "relation_type": "contains", "weight": 1, "generated": True})
        for venue in venues:
            key = self.kg_node_key("venue", venue["id"], venue["name"])
            nodes[key] = {"id": key, "type": "venue", "name": venue["name"], "generated": True}
        return {"nodes": list(nodes.values()), "edges": edges}

    def kg_node_key(self, node_type, node_id, name):
        return f"{node_type}:{node_id or name}"

    def admin_overview(self):
        return cache_get_or_set(cache_keys.ADMIN_OVERVIEW, self._admin_overview)

    def _admin_overview(self):
        with session_scope() as session:
            return FitnessRepository(session).admin_overview()

    def admin_users(self):
        with session_scope() as session:
            data = FitnessRepository(session).admin_users()
        return {"users": data["users"], "role_stats": data["role_stats"], "user_segments": data["segment_stats"]}

    def admin_user_detail(self, query):
        user_id = parse_qs(query).get("id", [None])[0]
        if not user_id:
            return {"error": "缺少用户 ID"}
        with session_scope() as session:
            return FitnessRepository(session).admin_user_detail(int(user_id))

    def admin_logs(self):
        with session_scope() as session:
            return {"logs": FitnessRepository(session).admin_logs(), "audit_rules": ["ORM 写入审计", "管理员操作记录"]}

    def admin_settings(self):
        with session_scope() as session:
            return {"settings": [self.decorate_admin_setting(row) for row in FitnessRepository(session).settings()]}

    def admin_setting_defaults(self):
        return {
            "system_name": ("系统名称", "前端和后台展示名称", True),
            "allow_registration": ("开放注册", "是否允许新用户注册", True),
            "cache_enabled": ("启用缓存", "热点数据使用 Redis cache-aside", True),
        }

    def decorate_admin_setting(self, row):
        label, description, default_enabled = self.admin_setting_defaults().get(row["dict_key"], (row["dict_key"], "", True))
        return {**row, "label": label, "description": description, "default_enabled": default_enabled}

    def admin_roles(self):
        defaults = [
            {"dict_key": "admin", "dict_value": "管理员|系统管理权限", "enabled": True},
            {"dict_key": "user", "dict_value": "普通用户|训练和推荐权限", "enabled": True},
        ]
        with session_scope() as session:
            custom_rows = FitnessRepository(session).roles()
        return {"roles": [*defaults, *custom_rows]}

    def save_admin_user(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        username = (body.get("username") or "").strip()
        if not username:
            return {"error": "请填写账号"}
        password_hash = hash_password(body["password"]) if body.get("password") else None
        with session_scope() as session:
            repo = FitnessRepository(session)
            user_id = repo.save_user_admin(body, password_hash)
            repo.save_admin_log(admin["id"], "保存后台账号", f"账号 {username} 已保存")
            user = repo.user_by_id(user_id)
        return {"user": user}

    def delete_admin_user(self, body):
        admin = self.current_admin(body=body)
        user_id = int(body.get("id") or 0)
        if not admin:
            return {"error": "需要管理员权限"}
        if user_id == admin["id"]:
            return {"error": "不能删除当前登录的管理员账号"}
        with session_scope() as session:
            repo = FitnessRepository(session)
            repo.delete_user(user_id)
            repo.save_admin_log(admin["id"], "删除账号", f"账号 {user_id} 已删除")
        return {"message": "账号已删除"}

    def save_admin_log(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        with session_scope() as session:
            repo = FitnessRepository(session)
            log_id = repo.save_admin_log(admin["id"], body.get("action", "管理员操作"), body.get("detail", ""))
            logs = repo.admin_logs(1)
        return {"log": logs[0] if logs else {"id": log_id}}

    def save_announcement(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        title = (body.get("title") or "").strip()
        content = (body.get("content") or "").strip()
        if not title or not content:
            return {"error": "请填写公告标题和内容"}
        with session_scope() as session:
            repo = FitnessRepository(session)
            announcement_id = repo.save_announcement(title, content, body.get("level", "info"))
            repo.save_admin_log(admin["id"], "发布公告", title)
        return {"announcement": {"id": announcement_id, "title": title, "content": content, "level": body.get("level", "info")}}

    def save_admin_settings(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        saved = []
        with session_scope() as session:
            repo = FitnessRepository(session)
            for index, item in enumerate(body.get("settings") or [], start=1):
                key = item.get("dict_key") or item.get("key")
                if not key:
                    continue
                value = item.get("dict_value") or item.get("value") or ""
                repo.upsert_dictionary("admin_setting", key, value, bool(item.get("enabled", True)), index)
                saved.append({**item, "dict_key": key, "dict_value": value})
            repo.save_admin_log(admin["id"], "保存系统设置", f"更新 {len(saved)} 项后台设置")
        return {"settings": saved}

    def save_admin_exercise(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        name = (body.get("name") or "").strip()
        if not name:
            return {"error": "请填写课程名称"}
        payload = {
            **body,
            "name": name,
            "category": body.get("category") or "综合训练",
            "difficulty": int(body.get("difficulty") or 1),
            "target": body.get("target") or "综合体能",
            "equipment": body.get("equipment") or "徒手",
            "standard_json": body.get("standard_json") or "{}",
        }
        with session_scope() as session:
            repo = FitnessRepository(session)
            exercise_id = repo.save_exercise(payload)
            repo.save_admin_log(admin["id"], "保存课程", f"课程 {name} 已写入")
            exercise = next((item for item in repo.exercises() if item["id"] == exercise_id), None)
        return {"exercise": exercise}

    def delete_admin_exercise(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        if body.get("confirm") is not True:
            return {"error": "删除动作需要 confirm=true"}
        exercise_id = body.get("id")
        if not exercise_id:
            return {"error": "缺少动作 ID"}
        with session_scope() as session:
            repo = FitnessRepository(session)
            deleted = repo.delete_exercise(int(exercise_id))
            if deleted:
                repo.save_admin_log(admin["id"], "删除课程", str(exercise_id))
        return {"deleted": deleted, "id": int(exercise_id)} if deleted else {"error": "动作不存在"}

    def save_admin_role(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        name = (body.get("name") or body.get("dict_key") or "").strip()
        if not name:
            return {"error": "请填写角色名称"}
        key = body.get("dict_key") or name.lower().replace(" ", "_")
        value = body.get("dict_value") or f"{name}|{body.get('description', '')}"
        with session_scope() as session:
            FitnessRepository(session).upsert_dictionary("admin_role", key, value, True, int(body.get("sort_order", 20)))
        return {"role": {"dict_key": key, "dict_value": value, "enabled": True}}

    def save_equipment(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        required = ("name", "category", "location", "latitude", "longitude")
        if any(body.get(key) in (None, "") for key in required):
            return {"error": "请填写器材名称、类型、位置和经纬度"}
        with session_scope() as session:
            repo = FitnessRepository(session)
            equipment_id = repo.save_equipment(body)
            repo.save_admin_log(admin["id"], "保存器材", body["name"])
            equipment = next((item for item in repo.equipment_with_venue() if item["id"] == equipment_id), None)
        return {"equipment": equipment}

    def delete_equipment(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        with session_scope() as session:
            repo = FitnessRepository(session)
            repo.delete_equipment(int(body.get("id")))
            repo.save_admin_log(admin["id"], "删除器材", str(body.get("id")))
        return {"message": "器材已删除"}

    def save_admin_venue(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        required = ("name", "location", "latitude", "longitude", "equipment")
        if any(body.get(key) in (None, "") for key in required):
            return {"error": "请填写场馆名称、位置、经纬度和设施"}
        payload = {
            **body,
            "capacity": int(body.get("capacity") or 50),
            "crowd_index": int(body.get("crowd_index") or 0),
            "air_quality": int(body.get("air_quality") or 50),
            "open_hours": body.get("open_hours") or "06:00-22:00",
            "density_score": float(body.get("density_score") or body.get("crowd_index") or 0),
        }
        with session_scope() as session:
            repo = FitnessRepository(session)
            venue_id = repo.save_venue(payload)
            repo.save_admin_log(admin["id"], "保存场馆", payload["name"])
            venue = next((item for item in repo.venues(admin_fields=True) if item["id"] == venue_id), None)
        return {"venue": venue}

    def delete_admin_venue(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        with session_scope() as session:
            repo = FitnessRepository(session)
            repo.delete_venue(int(body.get("id")))
            repo.save_admin_log(admin["id"], "删除场馆", str(body.get("id")))
        return {"message": "场馆已删除"}

    def save_knowledge_edge(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        required = ("source_type", "source_name", "relation_type", "target_type", "target_name")
        if any(not body.get(key) for key in required):
            return {"error": "请填写完整的知识图谱关系"}
        with session_scope() as session:
            repo = FitnessRepository(session)
            edge_id = repo.save_edge(body)
            repo.save_admin_log(admin["id"], "保存知识图谱关系", f"{body['source_name']} -> {body['target_name']}")
            edge = next((item for item in repo.knowledge_edges() if item["id"] == edge_id), None)
        return {"edge": edge}

    def delete_knowledge_edge(self, body):
        admin = self.current_admin(body=body)
        if not admin:
            return {"error": "需要管理员权限"}
        with session_scope() as session:
            repo = FitnessRepository(session)
            repo.delete_edge(int(body.get("id")))
            repo.save_admin_log(admin["id"], "删除知识图谱关系", str(body.get("id")))
        return {"message": "关系已删除"}
