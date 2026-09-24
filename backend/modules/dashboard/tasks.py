"""Deliver transactional notification events through live and push channels."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from core.celery_app import celery_app
from core.database import AsyncSessionLocal
from core.live import publish_live_event
from core.notifications import send_push_notification
from modules.auth.models import PushSubscription
from modules.dashboard.models import NotificationEvent


def push_targets(payload: dict, subscriptions: list) -> list:
    """Subscriptions a notification may be pushed to.

    Recipients are opt-in: `userId` / `userIds` address specific users, and only
    an explicit `broadcast` reaches every subscriber. An event without either
    (it used to go to everyone) is pushed to no one — paper decisions and other
    team-internal news must not reach all users of all events.
    """
    if payload.get("broadcast"):
        return list(subscriptions)
    user_ids = set(payload.get("userIds") or [])
    if payload.get("userId"):
        user_ids.add(payload["userId"])
    return [s for s in subscriptions if s.user_id in user_ids]


@celery_app.task(name="notifications.deliver_outbox")
def deliver_outbox() -> None:
    async def run() -> None:
        async with AsyncSessionLocal() as db:
            items = list(
                (
                    await db.execute(
                        select(NotificationEvent)
                        .where(NotificationEvent.status == "pending")
                        .order_by(NotificationEvent.created_at)
                        .limit(100)
                    )
                ).scalars()
            )
            subscriptions = list((await db.execute(select(PushSubscription))).scalars())
            for item in items:
                item.attempts += 1
                try:
                    if item.event_id and item.payload.get("publicLive"):
                        await publish_live_event(item.event_id, item.event_type, item.payload)
                    title = item.payload.get("title") or item.event_type.replace("_", " ").title()
                    body = item.payload.get("message") or item.payload.get("body") or ""
                    targets = push_targets(item.payload, subscriptions)
                    if body and targets:
                        await asyncio.gather(
                            *(
                                send_push_notification(
                                    subscription.endpoint,
                                    subscription.p256dh,
                                    subscription.auth,
                                    title,
                                    body,
                                    f"/events/{item.event_id}/dashboard" if item.event_id else "/",
                                )
                                for subscription in targets
                            ),
                            return_exceptions=True,
                        )
                    item.status = "delivered"
                    item.processed_at = datetime.now(UTC)
                    item.last_error = None
                except Exception as exc:
                    item.last_error = str(exc)[:2000]
                    if item.attempts >= 5:
                        item.status = "failed"
            await db.commit()

    asyncio.run(run())
