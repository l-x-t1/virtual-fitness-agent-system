from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.repositories import FitnessRepository, session_scope

router = APIRouter(tags=["WebSocket"])


class TrainingConnectionManager:
    def __init__(self):
        self.connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.connections[user_id].add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        self.connections[user_id].discard(websocket)
        if not self.connections[user_id]:
            self.connections.pop(user_id, None)


manager = TrainingConnectionManager()


def message(message_type: str, data, request_id: str | None = None):
    return {
        "type": message_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
        "request_id": request_id or str(uuid4()),
    }


@router.websocket("/ws/training")
async def training_socket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    try:
        payload = decode_access_token(token or "")
        with session_scope() as session:
            user = FitnessRepository(session).user_by_id(int(payload["sub"]))
        if not user:
            raise ValueError("user not found")
    except Exception:
        await websocket.close(code=4401, reason="invalid token")
        return

    user_id = int(payload["sub"])
    await manager.connect(user_id, websocket)
    await websocket.send_json(message("connected", {"user_id": user_id}))
    try:
        while True:
            incoming = await websocket.receive_json()
            msg_type = incoming.get("type")
            request_id = incoming.get("request_id")
            if msg_type == "ping":
                await websocket.send_json(message("pong", {}, request_id))
            elif msg_type in {"training.start", "pose.score", "training.progress"}:
                await websocket.send_json(message(f"{msg_type}.ack", incoming.get("data", {}), request_id))
            else:
                await websocket.send_json(message("error", {"message": "不支持的消息类型"}, request_id))
    except (WebSocketDisconnect, RuntimeError):
        manager.disconnect(user_id, websocket)
    except Exception:
        await websocket.send_json(message("error", {"message": "消息格式错误"}))
        manager.disconnect(user_id, websocket)
