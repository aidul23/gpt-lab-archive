"""Deduplicate unified pipeline records across sources."""
from services.api_client_utils import normalize_doi
from services.identity_verification import normalize_arxiv_id
from services.pipeline.normalize import merge_records, normalize_title


def record_keys(record):
    """Return dedupe keys in priority order for a record."""
    keys = []
    doi = normalize_doi(record.get("doi"))
    if doi:
        keys.append(("doi", doi.lower()))
    arxiv_id = normalize_arxiv_id(record.get("arxiv_id"))
    if arxiv_id:
        keys.append(("arxiv", arxiv_id))
    title = normalize_title(record.get("title"))
    year = record.get("year")
    if title and year:
        keys.append(("title_year", f"{title}|{year}"))
    elif title:
        keys.append(("title", title))
    return keys


def dedupe_records(records):
    """
    Merge duplicate records.

    Priority: DOI → arXiv ID → normalized title + year → title.
    """
    merged = []
    index_by_key = {}

    for record in records or []:
        existing_idx = None
        for key in record_keys(record):
            if key in index_by_key:
                existing_idx = index_by_key[key]
                break

        if existing_idx is None:
            existing_idx = len(merged)
            merged.append(record)
        else:
            merged[existing_idx] = merge_records(merged[existing_idx], record)

        for key in record_keys(merged[existing_idx]):
            index_by_key[key] = existing_idx

    return merged


def find_matching_index(records, candidate):
    """Return index of a matching record in a list, or None."""
    candidate_keys = set(record_keys(candidate))
    if not candidate_keys:
        return None
    for index, record in enumerate(records):
        if candidate_keys.intersection(record_keys(record)):
            return index
    return None
