from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.controllers.auth import envelope
from app.dependencies.auth import require_admin
from app.models.admin import (
    AdminLogCreate,
    AdminSettingsUpdate,
    AdminUserSave,
    AnnouncementCreate,
    EquipmentSave,
    ExerciseSave,
    KnowledgeEdgeSave,
    RoleSave,
    VenueSave,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/api/admin", tags=["管理端"])


async def invoke(request: Request, admin: dict, method: str, *args):
    service = AdminService(admin, request.url.query)
    data = await run_in_threadpool(getattr(service, method), *args)
    return envelope(request, data)


@router.get("/equipment")
async def get_equipment(request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "equipment")


@router.post("/equipment")
async def save_equipment(body: EquipmentSave, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "save_equipment", body.model_dump(mode="json"))


@router.delete("/equipment/{item_id}")
async def delete_equipment(item_id: int, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "delete_equipment", item_id)


@router.get("/equipment-map")
async def equipment_map(request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "equipment_map")


@router.get("/knowledge-graph")
async def knowledge_graph(request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "knowledge_graph")


@router.post("/knowledge-graph")
async def save_knowledge_edge(body: KnowledgeEdgeSave, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "save_knowledge_edge", body.model_dump())


@router.delete("/knowledge-graph/{item_id}")
async def delete_knowledge_edge(item_id: int, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "delete_knowledge_edge", item_id)


@router.get("/overview")
async def overview(request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "overview")


@router.get("/users")
async def users(request: Request, admin=Depends(require_admin)):
    response = await invoke(request, admin, "users")
    for user in response["data"].get("users", []):
        user.pop("password", None)
    return response


@router.get("/user")
async def user_detail(request: Request, id: int = Query(gt=0), admin=Depends(require_admin)):
    response = await invoke(request, admin, "user_detail", id)
    response["data"].get("user", {}).pop("password", None)
    return response


@router.post("/user")
async def save_user(body: AdminUserSave, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "save_user", body.model_dump(exclude_none=True))


@router.delete("/user/{item_id}")
async def delete_user(item_id: int, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "delete_user", item_id)


@router.get("/venues")
async def venues(request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "venues", request.url.query)


@router.post("/venue")
async def save_venue(body: VenueSave, request: Request, admin=Depends(require_admin)):
    data = body.model_dump(exclude_none=True)
    if body.density_score is None:
        data["density_score"] = body.crowd_index
    return await invoke(request, admin, "save_venue", data)


@router.delete("/venue/{item_id}")
async def delete_venue(item_id: int, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "delete_venue", item_id)


@router.get("/logs")
async def logs(request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "logs")


@router.post("/logs")
async def save_log(body: AdminLogCreate, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "save_log", body.model_dump())


@router.post("/announcement")
async def save_announcement(body: AnnouncementCreate, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "save_announcement", body.model_dump())


@router.get("/settings")
async def settings(request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "settings")


@router.post("/settings")
async def save_settings(body: AdminSettingsUpdate, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "save_settings", body.model_dump())


@router.post("/exercise")
async def save_exercise(body: ExerciseSave, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "save_exercise", body.model_dump(exclude_none=True))


@router.get("/roles")
async def roles(request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "roles")


@router.post("/role")
async def save_role(body: RoleSave, request: Request, admin=Depends(require_admin)):
    return await invoke(request, admin, "save_role", body.model_dump(exclude_none=True))


# ============================================================
# FeatureFlag 管理接口
# ============================================================

@router.get("/features", summary="特性开关列表")
async def feature_list(request: Request, admin=Depends(require_admin)):
    from app.feature_flags.service import get_feature_flag_service
    ff = get_feature_flag_service()
    return envelope(request, {"features": ff.list_all()})


@router.get("/features/{feature_name}", summary="检查特性对特定用户的放量状态")
async def feature_check(feature_name: str, user_id: int, request: Request, admin=Depends(require_admin)):
    from app.feature_flags.service import get_feature_flag_service
    ff = get_feature_flag_service()
    return envelope(request, {
        "feature": feature_name,
        "user_id": user_id,
        "enabled": ff.is_enabled(feature_name, user_id),
        "percentage": ff.get_percentage(feature_name),
    })


@router.post("/features/{feature_name}", summary="设置特性放量百分比")
async def feature_set(feature_name: str, percentage: int = 0, request: Request = None, admin=Depends(require_admin)):
    from app.feature_flags.service import get_feature_flag_service
    ff = get_feature_flag_service()
    ff.set_percentage(feature_name, percentage)
    return envelope(request, {
        "feature": feature_name,
        "percentage": ff.get_percentage(feature_name),
    })
