from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services import ws_manager

router = APIRouter(tags=["stream"])


@router.websocket("/ws/dashboards/{dashboard_id}")
async def dashboard_stream(websocket: WebSocket, dashboard_id: str):
    await websocket.accept()
    client_id = f"{dashboard_id}:{id(websocket)}"
    await ws_manager.register(client_id, websocket)
    try:
        while True:
            try:
                message = await websocket.receive_json()
                for topic in message.get("subscribe", []):
                    ws_manager.hub.subscribe(client_id, topic)
                    ws_manager.ensure_reader(topic)
            except WebSocketDisconnect:
                raise
            except Exception:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.unregister(client_id)
