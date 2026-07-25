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
                    user_id = item.payload.get("userId")
                    targets = [
                        subscription
                        for subscription in subscriptions
                        if not user_id or subscription.user_id == user_id
                    ]
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
