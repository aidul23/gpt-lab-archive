"""
Tier 3 only: arXiv author-name search as review candidates.

IMPORTANT: Never auto-publish these results. arXiv has no ORCID disambiguation;
exact-name queries (au:"Full Name") still collide for common names. Hits must
pass Tier 3 scoring and manual admin confirmation.
"""
from services import arxiv_client
from services.author_matching import names_refer_to_same_person
from services.identity_verification import normalize_arxiv_id
from services.pipeline.dedupe import record_keys
from services.pipeline.normalize import unify_record

import config


def fetch_arxiv_name_candidates(member_name, *, max_results=None, exclude_records=None):
    """
    Query arXiv with an exact quoted author name and return Tier 3-shaped records.

    Only keeps entries whose author list strictly matches ``member_name``.
    Drops anything already covered by ``exclude_records`` (usually Tier 1/2).
    """
    member_name = (member_name or "").strip()
    if not member_name:
        return []

    max_results = max_results or config.ARXIV_NAME_CANDIDATE_MAX_RESULTS
    query = f'au:"{member_name}"'
    try:
        raw_works = arxiv_client.fetch_works(query, max_results=max_results)
    except Exception:
        return []

    excluded_keys = set()
    for record in exclude_records or []:
        excluded_keys.update(record_keys(record))

    candidates = []
    seen_arxiv = set()
    for work in raw_works:
        if not _lists_member(work, member_name):
            continue

        arxiv_id = normalize_arxiv_id(work.get("arxiv_id") or work.get("source_id"))
        if arxiv_id and arxiv_id in seen_arxiv:
            continue
        if arxiv_id:
            seen_arxiv.add(arxiv_id)

        record = unify_record(
            work,
            tier=3,
            match_reason="arxiv_name_exact",
            source_name="arxiv",
        )
        if arxiv_id:
            record["arxiv_id"] = arxiv_id

        # Skip if already present in Tier 1/2 (or other excludes).
        if excluded_keys.intersection(record_keys(record)):
            continue

        candidates.append(record)

    return candidates


def _lists_member(work, member_name):
    for author in work.get("authors") or []:
        name = author.get("author_name") if isinstance(author, dict) else author
        if names_refer_to_same_person(name, member_name):
            return True
    return False
