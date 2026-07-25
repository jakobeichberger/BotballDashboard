"""Redis-backed event stream shared by every API instance."""

import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from core.config import get_settings
from core.logging import get_logger

logger = get_logger("live")


def _channel(event_id: str | None) -> str:
    return f"botball:live:{event_id or 'all'}"


async def publish_live_event(event_id: str, event: str, payload: dict | None = None) -> bool:
    """Publish to the event channel and the backwards-compatible global channel."""
    message = json.dumps(
        {
            "event": event,
            "eventId": event_id,
            "payload": payload or {},
            "sentAt": datetime.now(UTC).isoformat(),
        }
    )
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await redis.publish(_channel(event_id), message)
        await redis.publish(_channel(None), message)
        return True
    except Exception as exc:
        logger.warning("live_publish_failed", event_id=event_id, error=str(exc))
        return False
    finally:
        await redis.aclose()


async def stream_live_events(websocket: WebSocket, event_id: str | None) -> None:
    """Forward a Redis Pub/Sub channel to one WebSocket client."""
    await websocket.accept()
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    receiver: asyncio.Task[str] | None = None
    try:
        await pubsub.subscribe(_channel(event_id))
        await websocket.send_json({"event": "connection", "payload": {"status": "connected"}})
        receiver = asyncio.create_task(websocket.receive_text())
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                await websocket.send_text(message["data"])
            if receiver.done():
                # Any client message is a keep-alive ping. A disconnect raises here.
                receiver.result()
                await websocket.send_json({"event": "pong"})
                receiver = asyncio.create_task(websocket.receive_text())
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("live_stream_failed", event_id=event_id, error=str(exc))
        with suppress(Exception):
            await websocket.send_json(
                {
                    "event": "connection",
                    "payload": {"status": "disconnected", "retry": True},
                }
            )
            await websocket.close(code=1013)
    finally:
        if receiver:
            receiver.cancel()
            with suppress(asyncio.CancelledError):
                await receiver
        with suppress(Exception):
            await pubsub.unsubscribe(_channel(event_id))
            await pubsub.aclose()
            await redis.aclose()
