from app.services.fitness_service import FitnessService


class AdminService:
    """Administrator domain facade with no dependency on FastAPI request objects."""

    def __init__(self, admin_user: dict, query: str = ""):
        self.operations = FitnessService(path=f"/api/admin?{query}", admin_user=admin_user)

    def equipment(self):
        return self.operations.admin_equipment()

    def equipment_map(self):
        return self.operations.admin_equipment_map()

    def knowledge_graph(self):
        return self.operations.admin_knowledge_graph()

    def overview(self):
        return self.operations.admin_overview()

    def users(self):
        return self.operations.admin_users()

    def user_detail(self, user_id: int):
        return self.operations.admin_user_detail(f"id={user_id}")

    def venues(self, query: str):
        return self.operations.admin_venues(query)

    def logs(self):
        return self.operations.admin_logs()

    def settings(self):
        return self.operations.admin_settings()

    def roles(self):
        return self.operations.admin_roles()

    def save_equipment(self, data: dict):
        return self.operations.save_equipment(data)

    def delete_equipment(self, item_id: int):
        return self.operations.delete_equipment({"id": item_id})

    def save_knowledge_edge(self, data: dict):
        return self.operations.save_knowledge_edge(data)

    def delete_knowledge_edge(self, item_id: int):
        return self.operations.delete_knowledge_edge({"id": item_id})

    def save_user(self, data: dict):
        return self.operations.save_admin_user(data)

    def delete_user(self, item_id: int):
        return self.operations.delete_admin_user({"id": item_id})

    def save_venue(self, data: dict):
        return self.operations.save_admin_venue(data)

    def delete_venue(self, item_id: int):
        return self.operations.delete_admin_venue({"id": item_id})

    def save_log(self, data: dict):
        return self.operations.save_admin_log(data)

    def save_announcement(self, data: dict):
        return self.operations.save_announcement(data)

    def save_settings(self, data: dict):
        return self.operations.save_admin_settings(data)

    def save_exercise(self, data: dict):
        return self.operations.save_admin_exercise(data)

    def delete_exercise(self, item_id: int, confirm: bool = False):
        return self.operations.delete_admin_exercise({"id": item_id, "confirm": confirm})

    def save_role(self, data: dict):
        return self.operations.save_admin_role(data)
