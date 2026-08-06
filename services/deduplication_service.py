"""Simple publication deduplication helpers for future sync workflows."""
import re

from database.db import Publication


def normalize_title(title):
    """
    Normalize a title for comparison.

    Rules:
    - lowercase
    - remove punctuation
    - collapse whitespace
    """
    if not title:
        return ""
    text = title.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_same_publication(existing, candidate):
    """
    Determine whether two publication records refer to the same work.

    Priority:
    1. Matching DOI
    2. Matching arXiv ID
    3. Matching source + source_id
    4. Matching normalized title + year (fallback: title only)
    """
    existing_doi = (existing.doi or "").strip().lower()
    candidate_doi = (candidate.get("doi") or "").strip().lower()
    if existing_doi and candidate_doi and existing_doi == candidate_doi:
        return True

    from services.identity_verification import normalize_arxiv_id

    existing_arxiv = normalize_arxiv_id(
        getattr(existing, "arxiv_id", None) or existing.source_id
        if (existing.source or "").lower() == "arxiv"
        else getattr(existing, "arxiv_id", None)
    )
    candidate_arxiv = normalize_arxiv_id(
        candidate.get("arxiv_id")
        or (candidate.get("source_id") if (candidate.get("source") or "").lower() == "arxiv" else None)
    )
    if existing_arxiv and candidate_arxiv and existing_arxiv == candidate_arxiv:
        return True

    existing_source = (existing.source or "").strip().lower()
    candidate_source = (candidate.get("source") or "").strip().lower()
    existing_source_id = (existing.source_id or "").strip().lower()
    candidate_source_id = (candidate.get("source_id") or "").strip().lower()
    if (
        existing_source
        and candidate_source
        and existing_source_id
        and candidate_source_id
        and existing_source == candidate_source
        and existing_source_id == candidate_source_id
    ):
        return True

    existing_title = normalize_title(existing.title)
    candidate_title = normalize_title(candidate.get("title"))
    if existing_title and candidate_title and existing_title == candidate_title:
        existing_year = existing.year
        candidate_year = candidate.get("year")
        if existing_year and candidate_year:
            return int(existing_year) == int(candidate_year)
        return True

    return False


def find_duplicate(candidate, publications=None):
    """
    Find an existing publication that matches the candidate metadata.

    candidate: dict with optional keys doi, source, source_id, title
    publications: optional iterable; defaults to all publications in DB
    """
    records = publications if publications is not None else Publication.query.all()

    for publication in records:
        if is_same_publication(publication, candidate):
            return publication
    return None
