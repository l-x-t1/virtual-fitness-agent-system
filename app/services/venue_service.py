from app.services.fitness_service import FitnessService


class VenueService:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def exercises(self):
        return {"exercises": self.coordinator.exercises()}

    def venues(self):
        return {"venues": self.coordinator.venues()}

    def enrich(self, query: str):
        return FitnessService().enrich_venues(query)
