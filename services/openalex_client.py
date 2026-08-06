"""OpenAlex API client."""
import re

from services.api_client_utils import get_json, map_work_type, normalize_doi, parse_year


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


def fetch_works(author_id, max_results=50):
    """Fetch and normalize works for an OpenAlex author."""
    author_url = normalize_author_id(author_id)
    if not author_url:
        return []

    url = "https://api.openalex.org/works"
    params = {
        "filter": f"authorships.author.id:{author_url}",
        "sort": "publication_date:desc",
        "per-page": max_results,
    }
    payload = get_json(url, "openalex-sync", params=params)
    candidates = []

    for work in payload.get("results", []):
        title = (work.get("title") or "").strip()
        if not title:
            continue

        doi = normalize_doi(work.get("doi"))
        venue = None
        primary_location = work.get("primary_location") or {}
        source = primary_location.get("source") or {}
        venue = (source.get("display_name") or "").strip() or None

        openalex_id = work.get("id", "")
        openalex_id = re.sub(r"^https://openalex.org/", "", openalex_id)
        work_type = map_work_type(work.get("type"))
        is_preprint = (work.get("type") or "").lower() == "preprint"

        candidates.append(
            {
                "title": title,
                "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
                "year": parse_year(work.get("publication_year")),
                "publication_date": (work.get("publication_date") or "").strip() or None,
                "type": work_type,
                "venue": venue,
                "doi": doi,
                "url": work.get("id") or (f"https://doi.org/{doi}" if doi else None),
                "pdf_url": (primary_location.get("pdf_url") or "").strip() or None,
                "source": "openalex",
                "source_id": openalex_id or None,
                "is_preprint": is_preprint,
                "is_published": not is_preprint,
                "authors": _extract_authors(work.get("authorships") or []),
            }
        )

    return candidates


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
    for position, _, name in ranked:
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
