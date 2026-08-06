"""Optional background scheduler for automatic publication sync."""
import os

import config


def init_auto_sync(app):
    """Start a background scheduler when automatic sync is enabled."""
    if not config.AUTO_SYNC_ENABLED:
        return None

    # Avoid duplicate schedulers when Flask debug reloader spawns a parent process.
    if config.DEBUG and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return None

    from apscheduler.schedulers.background import BackgroundScheduler

    from services import sync_service

    scheduler = BackgroundScheduler(daemon=True)

    def run_sync_job():
        with app.app_context():
            sync_service.sync_all_members(active_only=config.AUTO_SYNC_ACTIVE_ONLY)

    scheduler.add_job(
        run_sync_job,
        trigger="interval",
        hours=config.AUTO_SYNC_INTERVAL_HOURS,
        id="sync_all_members",
        replace_existing=True,
    )
    scheduler.start()

    if config.AUTO_SYNC_ON_STARTUP:
        run_sync_job()

    return scheduler
