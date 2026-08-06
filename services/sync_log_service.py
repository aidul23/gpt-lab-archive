"""Sync log database operations."""
from database.db import SyncLog, db, utcnow


def start_log(source):
    """Create a sync log entry when a sync starts."""
    log = SyncLog(source=source, started_at=utcnow(), status="running")
    db.session.add(log)
    db.session.commit()
    return log


def finish_log(log, status, message):
    """Mark a sync log entry as finished."""
    log.status = status
    log.message = message
    log.finished_at = utcnow()
    db.session.commit()
    return log


def get_recent_logs(limit=20):
    """Return recent sync log entries."""
    return SyncLog.query.order_by(SyncLog.started_at.desc()).limit(limit).all()
