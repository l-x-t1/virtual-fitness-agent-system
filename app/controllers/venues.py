from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from app.controllers.auth import envelope
from fastapi import Depends
from app.dependencies.services import get_coordinator
from app.services.venue_service import VenueService

router = APIRouter(prefix="/api", tags=["场馆与动作"])


@router.get("/exercises")
async def exercises(request: Request, coordinator=Depends(get_coordinator)):
    return envelope(request, await run_in_threadpool(VenueService(coordinator).exercises))


@router.get("/venues")
async def venues(request: Request, coordinator=Depends(get_coordinator)):
    return envelope(request, await run_in_threadpool(VenueService(coordinator).venues))


@router.get("/venues/enrich")
async def enrich(request: Request, lat: float | None = None, lon: float | None = None,
                 coordinator=Depends(get_coordinator)):
    query = request.url.query
    data = await run_in_threadpool(VenueService(coordinator).enrich, query)
    return envelope(request, data)
