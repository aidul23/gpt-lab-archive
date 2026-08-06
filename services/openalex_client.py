"""OpenAlex API client.

Prefer ORCID-filtered work queries over Author IDs. OpenAlex Author IDs suffer
from split/merge (one person → many IDs; occasionally two people → one ID).
"""
import re
import time

import config
from services.api_client_utils import get_json, map_work_type, normalize_doi, parse_year
from services.identity_verification import normalize_arxiv_id
from services.orcid_client import normalize_orcid, orcid_url


def normalize_author_id(author_id):
    """Return a full OpenAlex author URL."""
    if not author_id:
        return None

    author_id = str(author_id).strip()
    if author_id.startswith("http"):
        return author_id
    if author_id.startswith("A"):
        return f"https://openalex.org/{author_id}"
    return f"https://openalex.org/A{author_id}"


def fetch_works_by_orcid(orcid, page_size=None, max_pages=None):
    """
    Fetch works linked to an ORCID via authorships.author.orcid.

    Returns (candidates, observed_openalex_author_ids).
    Only works that re-verify the ORCID on an authorship are included.
    """
    orcid = normalize_orcid(orcid)
    orcid_full = orcid_url(orcid)
    if not orcid_full:
        return [], []

    page_size = page_size or config.OPENALEX_PAGE_SIZE
    max_pages = max_pages or config.OPENALEX_MAX_PAGES

    url = "https://api.openalex.org/works"
    cursor = "*"
    candidates = []
    observed_author_ids = set()

    for _ in range(max_pages):
        params = {
            "filter": f"authorships.author.orcid:{orcid_full}",
            "sort": "publication_date:desc",
            "per-page": page_size,
            "cursor": cursor,
            "mailto": config.CONTACT_EMAIL,
        }
        payload = get_json(url, "openalex-sync", params=params)
        results = payload.get("results") or []
        if not results:
            break

        for work in results:
            candidate, author_ids = _normalize_work(work, required_orcid=orcid)
            if not candidate:
                continue
            candidates.append(candidate)
            observed_author_ids.update(author_ids)

        meta = payload.get("meta") or {}
        next_cursor = meta.get("next_cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        time.sleep(0.1)

    return candidates, sorted(observed_author_ids)


def fetch_works(author_id, max_results=50):
    """
    Legacy Author-ID fetch (not used by the ORCID-anchored pipeline).

    Kept for admin diagnostics only. Prefer fetch_works_by_orcid.
    """
    author_url = normalize_author_id(author_id)
    if not author_url:
        return []

    url = "https://api.openalex.org/works"
    params = {
        "filter": f"authorships.author.id:{author_url}",
        "sort": "publication_date:desc",
        "per-page": max_results,
        "mailto": config.CONTACT_EMAIL,
    }
    payload = get_json(url, "openalex-sync", params=params)
    candidates = []
    for work in payload.get("results", []):
        candidate, _ = _normalize_work(work, required_orcid=None)
        if candidate:
            candidates.append(candidate)
    return candidates


def work_has_orcid(work_or_authorships, orcid):
    """Return True when an authorship carries the given ORCID."""
    orcid = normalize_orcid(orcid)
    if not orcid:
        return False
    if isinstance(work_or_authorships, dict) and "authorships" in work_or_authorships:
        authorships = work_or_authorships.get("authorships") or []
    elif isinstance(work_or_authorships, dict) and "_raw_authorships" in work_or_authorships:
        authorships = work_or_authorships.get("_raw_authorships") or []
    else:
        authorships = work_or_authorships or []

    target = orcid.lower()
    for authorship in authorships:
        author = authorship.get("author") or {}
        author_orcid = normalize_orcid(author.get("orcid"))
        if author_orcid and author_orcid.lower() == target:
            return True
    return False


def _normalize_work(work, required_orcid=None):
    """Normalize one OpenAlex work; optionally require ORCID on authorship."""
    title = (work.get("title") or "").strip()
    if not title:
        return None, []

    authorships = work.get("authorships") or []
    observed_ids = []
    matched_author_ids = []
    if required_orcid:
        if not work_has_orcid(authorships, required_orcid):
            return None, []
        for authorship in authorships:
            author = authorship.get("author") or {}
            if normalize_orcid(author.get("orcid")) == normalize_orcid(required_orcid):
                author_id = author.get("id")
                if author_id:
                    short = re.sub(r"^https://openalex.org/", "", author_id)
                    matched_author_ids.append(short)
                    observed_ids.append(short)

    doi = normalize_doi(work.get("doi"))
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    venue = (source.get("display_name") or "").strip() or None
    source_type = (source.get("type") or "").lower()
    source_name = (source.get("display_name") or "").lower()

    openalex_id = work.get("id", "")
    openalex_id = re.sub(r"^https://openalex.org/", "", openalex_id)
    work_type = map_work_type(work.get("type"))
    is_preprint = (work.get("type") or "").lower() == "preprint" or "arxiv" in source_name

    arxiv_id = None
    for location in work.get("locations") or []:
        loc_source = location.get("source") or {}
        if "arxiv" in (loc_source.get("display_name") or "").lower():
            arxiv_id = normalize_arxiv_id(location.get("landing_page_url")) or normalize_arxiv_id(
                location.get("pdf_url")
            )
            if arxiv_id:
                break
    if not arxiv_id:
        arxiv_id = normalize_arxiv_id(primary_location.get("landing_page_url")) or normalize_arxiv_id(
            doi
        )

    affiliations = []
    for authorship in authorships:
        for institution in authorship.get("institutions") or []:
            affiliations.append(
                {
                    "name": institution.get("display_name"),
                    "ror": institution.get("ror"),
                    "id": institution.get("id"),
                }
            )

    concepts = []
    for concept in work.get("concepts") or []:
        concepts.append(
            {
                "id": concept.get("id"),
                "display_name": concept.get("display_name"),
                "score": concept.get("score"),
            }
        )

    candidate = {
        "title": title,
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "year": parse_year(work.get("publication_year")),
        "publication_date": (work.get("publication_date") or "").strip() or None,
        "type": work_type,
        "venue": venue,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "url": work.get("id") or (f"https://doi.org/{doi}" if doi else None),
        "pdf_url": (primary_location.get("pdf_url") or "").strip() or None,
        "source": "openalex",
        "source_id": openalex_id or None,
        "is_preprint": is_preprint,
        "is_published": not is_preprint,
        "authors": _extract_authors(authorships),
        "concepts": concepts,
        "affiliations": affiliations,
        "openalex_author_ids": matched_author_ids,
        "_orcid_verified": bool(required_orcid),
        "_raw_authorships": authorships,
        "_source_type": source_type,
    }
    return candidate, observed_ids


def _extract_authors(authorships):
    """Convert OpenAlex authorships to local author dicts."""
    ranked = []
    for index, authorship in enumerate(authorships):
        author = authorship.get("author") or {}
        name = (author.get("display_name") or "").strip()
        if not name:
            continue
        ranked.append(
            (
                _openalex_author_rank(authorship, index),
                index,
                name,
            )
        )

    ranked.sort(key=lambda item: (item[0], item[1]))
    authors = []
    for _, _, name in ranked:
        authors.append(
            {
                "author_name": name,
                "member_id": None,
                "author_position": len(authors) + 1,
            }
        )
    return authors


def _openalex_author_rank(authorship, fallback_index):
    """Convert OpenAlex author position values to a sortable rank."""
    position = authorship.get("author_position")
    if isinstance(position, int):
        return position
    if isinstance(position, str):
        value = position.lower()
        if value == "first":
            return 1
        if value == "middle":
            return 5000 + fallback_index
        if value == "last":
            return 9000
    return fallback_index + 1


def _reconstruct_abstract(inverted_index):
    """Rebuild abstract text from OpenAlex inverted index."""
    if not inverted_index:
        return None

    words = []
    for word, positions in inverted_index.items():
        for position in positions:
            words.append((position, word))
    words.sort()
    return " ".join(word for _, word in words) or None
