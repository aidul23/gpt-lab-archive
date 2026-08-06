"""arXiv API client."""
import re
import xml.etree.ElementTree as ET

import requests

import config
from services.api_client_utils import map_work_type, parse_year


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
ARXIV_API_URL = "https://export.arxiv.org/api/query"
FIELD_QUERY_RE = re.compile(
    r"^(all|au|ti|abs|co|jr|cat|id):",
    flags=re.IGNORECASE,
)


def fetch_by_id(arxiv_id):
    """
    Fetch a single arXiv preprint by ID.

    Safe for enrichment: this is an ID lookup, not an author-name search.
    """
    arxiv_id = (arxiv_id or "").strip()
    if not arxiv_id:
        return None
    # Strip version for query stability; API accepts versioned ids too.
    bare = re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE)
    results = fetch_works(f"id:{bare}", max_results=1)
    return results[0] if results else None


def fetch_works(query, max_results=10):
    """Search arXiv and return normalized preprint records."""
    query = (query or "").strip()
    if not query:
        return []

    search_query = _build_search_query(query)
    response = requests.get(
        ARXIV_API_URL,
        params={
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        headers={
            "User-Agent": (
                f"GPT-Lab-Archive/1.0 (arxiv-sync; mailto:{config.CONTACT_EMAIL})"
            )
        },
        timeout=config.API_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    root = ET.fromstring(response.text)
    candidates = []

    for entry in root.findall("atom:entry", ATOM_NS):
        title = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
        title = re.sub(r"\s+", " ", title)
        if not title:
            continue

        summary = (entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").strip()
        summary = re.sub(r"\s+", " ", summary) or None
        published = (entry.findtext("atom:published", default="", namespaces=ATOM_NS) or "").strip()
        year = parse_year(published[:4] if published else None)
        publication_date = published[:10] if published else None
        entry_id = (entry.findtext("atom:id", default="", namespaces=ATOM_NS) or "").strip()
        arxiv_id = _extract_arxiv_id(entry_id)
        # Store version-stripped id for dedupe / overrides.
        bare_id = re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE) if arxiv_id else None
        pdf_url = f"https://arxiv.org/pdf/{bare_id}.pdf" if bare_id else None

        authors = []
        for index, author in enumerate(entry.findall("atom:author", ATOM_NS), start=1):
            name = (author.findtext("atom:name", default="", namespaces=ATOM_NS) or "").strip()
            if name:
                authors.append(
                    {
                        "author_name": name,
                        "member_id": None,
                        "author_position": index,
                    }
                )

        candidates.append(
            {
                "title": title,
                "abstract": summary,
                "year": year,
                "publication_date": publication_date,
                "type": map_work_type("preprint"),
                "venue": "arXiv",
                "doi": None,
                "arxiv_id": bare_id,
                "url": entry_id or None,
                "pdf_url": pdf_url,
                "source": "arxiv",
                "source_id": bare_id or arxiv_id,
                "is_preprint": True,
                "is_published": False,
                "authors": authors,
            }
        )

    return candidates


def _build_search_query(query):
    """
    Build an arXiv search_query string.

    Fielded queries such as au:... are passed through unchanged.
    Bare text is searched across all fields.
    """
    if re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", query):
        return f"id:{query}"
    if FIELD_QUERY_RE.match(query):
        return query
    return f"all:{query}"


def _extract_arxiv_id(entry_id):
    """Extract an arXiv ID from an Atom entry URL."""
    if not entry_id:
        return None
    match = re.search(r"arxiv\.org/abs/([^/?#]+)", entry_id, flags=re.IGNORECASE)
    return match.group(1) if match else None
