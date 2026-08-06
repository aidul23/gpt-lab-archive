"""Application configuration."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# SQLite database file path
DATABASE_PATH = os.path.join(BASE_DIR, "database", "lab_publications.db")

# Flask settings
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
# Default to 5001 because macOS often reserves port 5000 for AirPlay Receiver.
PORT = int(os.environ.get("FLASK_PORT", "5001"))

# Admin authentication
# Set ADMIN_PASSWORD in production. Optionally set ADMIN_PASSWORD_HASH instead.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")

# External API settings
API_TIMEOUT_SECONDS = int(os.environ.get("API_TIMEOUT_SECONDS", "20"))

# Site branding (GPT Lab, Tampere University)
LAB_NAME = os.environ.get("LAB_NAME", "GPT Lab")
LAB_WEBSITE_URL = os.environ.get("LAB_WEBSITE_URL", "https://gpt-lab.eu/")
LAB_TAGLINE = os.environ.get(
    "LAB_TAGLINE",
    "An AI research lab at Tampere University, pioneering Generative AI in Software Engineering.",
)
ARCHIVE_TITLE = os.environ.get("ARCHIVE_TITLE", "Publications & Research Archive")
ARCHIVE_TAGLINE = os.environ.get(
    "ARCHIVE_TAGLINE",
    "A dedicated showcase for GPT Lab members' papers, research themes, and scholarly output.",
)
UNIVERSITY_NAME = os.environ.get("UNIVERSITY_NAME", "Tampere University")
UNIVERSITY_URL = os.environ.get("UNIVERSITY_URL", "https://www.tuni.fi/en")
SITE_NAME = os.environ.get("SITE_NAME", f"{LAB_NAME} {ARCHIVE_TITLE}")
SITE_DESCRIPTION = os.environ.get(
    "SITE_DESCRIPTION",
    (
        "Browse GPT Lab members, their publications and preprints, and research themes "
        "in one place. For news, projects, and services, visit the main GPT Lab website."
    ),
)
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "gpt-lab@tuni.fi")

# Automatic sync settings
AUTO_SYNC_ENABLED = os.environ.get("AUTO_SYNC_ENABLED", "0") == "1"
AUTO_SYNC_ON_STARTUP = os.environ.get("AUTO_SYNC_ON_STARTUP", "0") == "1"
AUTO_SYNC_INTERVAL_HOURS = int(os.environ.get("AUTO_SYNC_INTERVAL_HOURS", "24"))
AUTO_SYNC_ACTIVE_ONLY = os.environ.get("AUTO_SYNC_ACTIVE_ONLY", "1") == "1"

# Member photo uploads
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "members")
ALLOWED_PHOTO_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "5"))
