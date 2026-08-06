"""Run automatic publication sync for all lab members.

Usage:
    python scripts/sync_all.py

Schedule with cron, for example every day at 2 AM:
    0 2 * * * cd /path/to/gpt-lab-archive && ./venv/bin/python scripts/sync_all.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from services import sync_service


def main():
    with app.app_context():
        result = sync_service.sync_all_members(active_only=True)
        print(result.get("message", "Sync finished."))
        print(
            "Created: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {errors}".format(
                created=result.get("created", 0),
                updated=result.get("updated", 0),
                skipped=result.get("skipped", 0),
                errors=result.get("errors", 0),
            )
        )
        return 0 if result.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
