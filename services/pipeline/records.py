"""Shared helpers for unified pipeline records."""
from services.api_client_utils import normalize_doi
from services.identity_verification import normalize_arxiv_id


def empty_record():
    """Return a blank unified publication record."""
    return {
        "title": None,
        "authors": [],
        "year": None,
        "doi": None,
        "arxiv_id": None,
        "venue": None,
        "type": "article",
        "url": None,
        "pdf_url": None,
        "abstract": None,
        "publication_date": None,
        "source": None,
        "source_id": None,
        "is_preprint": False,
        "is_published": True,
        "matched_researcher_orcids": [],
        "confidence_tier": None,
        "match_reason": None,
        "sources": [],
        "concepts": [],
        "affiliations": [],
        "openalex_author_ids": [],
        "score": None,
        "score_breakdown": None,
    }


def author_names(record):
    """Return display names from a unified record or candidate."""
    names = []
    for author in record.get("authors") or []:
        if isinstance(author, str):
            name = author.strip()
        else:
            name = (author.get("author_name") or "").strip()
        if name:
            names.append(name)
    return names


def to_import_candidate(record):
    """Convert a unified pipeline record into publication_service import shape."""
    authors = []
    for index, author in enumerate(record.get("authors") or [], start=1):
        if isinstance(author, str):
            name = author.strip()
            member_id = None
            position = index
        else:
            name = (author.get("author_name") or "").strip()
            member_id = author.get("member_id")
            position = author.get("author_position") or index
        if not name:
            continue
        authors.append(
            {
                "author_name": name,
                "member_id": member_id,
                "author_position": position,
            }
        )

    arxiv_id = normalize_arxiv_id(record.get("arxiv_id"))
    source = record.get("source")
    source_id = record.get("source_id")
    if arxiv_id and (not source or source == "arxiv"):
        source = source or "arxiv"
        source_id = source_id or arxiv_id

    return {
        "title": (record.get("title") or "").strip(),
        "abstract": record.get("abstract"),
        "year": record.get("year"),
        "publication_date": record.get("publication_date"),
        "type": record.get("type") or "article",
        "venue": record.get("venue"),
        "doi": normalize_doi(record.get("doi")),
        "url": record.get("url"),
        "pdf_url": record.get("pdf_url"),
        "source": source,
        "source_id": source_id,
        "arxiv_id": arxiv_id,
        "is_preprint": bool(record.get("is_preprint")),
        "is_published": bool(record.get("is_published", not record.get("is_preprint"))),
        "authors": authors,
        "confidence_tier": record.get("confidence_tier"),
        "match_reason": record.get("match_reason"),
        "sources": list(record.get("sources") or []),
    }
