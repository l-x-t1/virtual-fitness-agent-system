from app.services.fitness_service import FitnessService


class TrainingService:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def submit_session(self, user_id: int, data: dict):
        return self.coordinator.submit_session(
            user_id,
            data["exercise_name"],
            data["score"],
            data["duration"],
        )

    def save_pose_record(self, user_id: int, data: dict):
        record_id = self.coordinator.save_pose_record(dict(data, user_id=user_id))
        return {"id": record_id, "message": "姿态识别记录已保存"}
