"""APScheduler setup — daily cron jobs for the application."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from virtual_labs.infrastructure.db.config import session_pool
from virtual_labs.infrastructure.redis import get_redis
from virtual_labs.usecases.course.expire_courses import expire_courses

scheduler = AsyncIOScheduler()


async def _run_expire_courses() -> None:
    """Scheduled job: expire courses past end_date. Uses Redis lock for single-execution."""
    redis = await get_redis()
    lock = redis.lock("cron:expire_courses", timeout=3600)

    if not await lock.acquire(blocking=False):
        logger.debug("expire_courses already running on another instance — skipping")
        return

    try:
        logger.info("Running scheduled job: expire_courses")
        async with session_pool.session() as db:
            summary = await expire_courses(db)
        logger.info(f"expire_courses finished: {summary}")
    except Exception as ex:  # noqa: BLE001
        logger.error(f"expire_courses job failed: {ex}")
    finally:
        try:
            await lock.release()
        except Exception:  # noqa: BLE001
            pass  # Lock expired or was already released


def start_scheduler() -> None:
    """Register jobs and start the scheduler."""
    scheduler.add_job(
        _run_expire_courses,
        trigger=CronTrigger(hour=2, minute=0, timezone="Europe/Zurich"),
        id="expire_courses",
        name="Drop enrolments in expired courses",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — expire_courses scheduled daily at 02:00 Europe/Zurich"
    )


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
