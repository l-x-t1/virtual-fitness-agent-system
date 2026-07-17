from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from app.controllers.auth import envelope
from app.dependencies.auth import get_current_user
from app.dependencies.services import get_coordinator
from app.models.training import PoseRecordSubmit, SessionSubmit
from app.services.training_service import TrainingService

router = APIRouter(prefix="/api", tags=["训练"])


@router.post("/session")
async def submit_session(body: SessionSubmit, request: Request, user=Depends(get_current_user),
                         coordinator=Depends(get_coordinator)):
    data = await run_in_threadpool(TrainingService(coordinator).submit_session, user["id"], body.model_dump())
    return envelope(request, data)


@router.post("/pose/record")
async def pose_record(body: PoseRecordSubmit, request: Request, user=Depends(get_current_user),
                      coordinator=Depends(get_coordinator)):
    data = await run_in_threadpool(TrainingService(coordinator).save_pose_record, user["id"], body.model_dump())
    return envelope(request, data)
