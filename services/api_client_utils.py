"""Shared helpers for external publication API clients."""
import re

import requests

import config


def api_headers(source):
    """Build a polite User-Agent header for external APIs."""
    return {
        "User-Agent": f"Lab-Publications-Portal/1.0 ({source}; mailto:{config.CONTACT_EMAIL})",
        "Accept": "application/json",
    }


def get_json(url, source, params=None):
    """Fetch JSON from an external API with basic error handling."""
    response = requests.get(
        url,
        params=params,
        headers=api_headers(source),
        timeout=config.API_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def normalize_doi(doi):
    """Strip common DOI URL prefixes and whitespace."""
    if not doi:
        return None
    doi = str(doi).strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi or None


def parse_year(value):
    """Convert a year-like value to an integer."""
    if value in (None, ""):
        return None
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def map_work_type(raw_type, default="article"):
    """Map external work types to local publication types."""
    if not raw_type:
        return default

    value = str(raw_type).lower()
    if "dataset" in value:
        return "dataset"
    if any(token in value for token in ("conference", "proceeding", "symposium")):
        return "conference"
    return default
