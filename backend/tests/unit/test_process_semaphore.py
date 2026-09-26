import asyncio

from core.concurrency import ProcessSemaphore


def test_limits_concurrency_and_survives_a_new_event_loop():
    slots = ProcessSemaphore(2)

    async def run() -> int:
        active = peak = 0

        async def job():
            nonlocal active, peak
            async with slots:
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*(job() for _ in range(6)))
        return peak

    # Two loops in a row (Celery tasks, tests): a plain module-level
    # asyncio.Semaphore bound to the first loop would fail in the second.
    assert asyncio.run(run()) == 2
    assert asyncio.run(run()) == 2
