from app.services.auth_service import public_user
from app.services.fitness_service import FitnessService


class UserService:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def dashboard(self, user: dict, query: str = ""):
        FitnessService().apply_request_location(user, query)
        return self.coordinator.dashboard(user)

    def update_profile(self, user: dict, data: dict):
        payload = dict(data, user_id=user["id"])
        result = FitnessService().update_profile(payload)
        result["user"] = public_user(result["user"])
        return result

    def sessions(self, user_id: int):
        return {"sessions": self.coordinator.sessions(user_id)}

    def badges(self, user_id: int):
        return {"badges": self.coordinator.badges(user_id)}

    def point_logs(self, user_id: int):
        return {"point_logs": self.coordinator.point_logs(user_id)}
