ADMIN_OVERVIEW = "fitness:admin:overview"
EQUIPMENT_MAP = "fitness:admin:equipment-map"
EXERCISES = "fitness:catalog:exercises"
KNOWLEDGE_GRAPH = "fitness:admin:knowledge-graph"
VENUES = "fitness:catalog:venues"


def dashboard(user_id: int) -> str:
    return f"fitness:user:{user_id}:dashboard"


def user_sessions(user_id: int) -> str:
    return f"fitness:user:{user_id}:sessions"


def user_badges(user_id: int) -> str:
    return f"fitness:user:{user_id}:badges"


def user_points(user_id: int) -> str:
    return f"fitness:user:{user_id}:points"


def user_related(user_id: int) -> list[str]:
    return [dashboard(user_id), user_sessions(user_id), user_badges(user_id), user_points(user_id)]


CATALOG_KEYS = [EXERCISES, VENUES, EQUIPMENT_MAP, KNOWLEDGE_GRAPH]
ADMIN_KEYS = [ADMIN_OVERVIEW, EQUIPMENT_MAP, KNOWLEDGE_GRAPH]
