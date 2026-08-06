"""Crossref API client."""
from services.api_client_utils import get_json, map_work_type, normalize_doi, parse_year


def fetch_work(doi):
    """Fetch and normalize a single Crossref work by DOI."""
    doi = normalize_doi(doi)
    if not doi:
        return None

    url = f"https://api.crossref.org/works/{doi}"
    payload = get_json(url, "crossref-sync")
    message = payload.get("message") or {}
    title_parts = message.get("title") or []
    title = (title_parts[0] if title_parts else "").strip()
    if not title:
        return None

    year = parse_year((message.get("issued") or {}).get("date-parts", [[None]])[0][0])
    pub_date = _extract_date(message.get("issued"))
    venue = _extract_venue(message)
    work_type = map_work_type(message.get("type"))
    url_value = (message.get("URL") or "").strip() or f"https://doi.org/{doi}"

    return {
        "title": title,
        "abstract": (message.get("abstract") or "").strip() or None,
        "year": year,
        "publication_date": pub_date,
        "type": work_type,
        "venue": venue,
        "doi": doi,
        "url": url_value,
        "pdf_url": None,
        "source": "crossref",
        "source_id": doi,
        "is_preprint": False,
        "is_published": True,
        "authors": _extract_authors(message.get("author") or []),
    }


def _extract_authors(authors):
    """Convert Crossref author records to local author dicts."""
    results = []
    for index, author in enumerate(authors, start=1):
        given = (author.get("given") or "").strip()
        family = (author.get("family") or "").strip()
        name = " ".join(part for part in (given, family) if part).strip()
        if not name:
            continue
        results.append(
            {
                "author_name": name,
                "member_id": None,
                "author_position": index,
            }
        )
    return results


def _extract_date(issued):
    """Convert Crossref issued block to YYYY-MM-DD."""
    if not issued:
        return None
    parts = (issued.get("date-parts") or [[None]])[0]
    if not parts or not parts[0]:
        return None

    year = str(parts[0])
    month = str(parts[1]).zfill(2) if len(parts) > 1 and parts[1] else "01"
    day = str(parts[2]).zfill(2) if len(parts) > 2 and parts[2] else "01"
    return f"{year}-{month}-{day}"


def _extract_venue(message):
    """Extract a human-readable venue from Crossref metadata."""
    for key in ("container-title", "publisher-name", "institution", "event"):
        value = message.get(key)
        if isinstance(value, list) and value:
            return value[0]
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
