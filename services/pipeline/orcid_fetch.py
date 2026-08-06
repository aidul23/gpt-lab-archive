"""Tier 1: fetch works claimed on an ORCID profile."""
from services import orcid_client
from services.identity_verification import normalize_arxiv_id
from services.pipeline.normalize import unify_record


def fetch_tier1_works(orcid):
    """
    Pull the researcher's ORCID works list and return unified Tier 1 records.

    Extracts DOI and arXiv IDs from external-ids. These are orcid_claimed.
    """
    orcid = orcid_client.normalize_orcid(orcid)
    if not orcid:
        return []

    raw_works = orcid_client.fetch_works(orcid, extract_all_external_ids=True)
    records = []
    for work in raw_works:
        arxiv_id = work.get("arxiv_id") or normalize_arxiv_id(work.get("url"))
        work = dict(work)
        work["arxiv_id"] = arxiv_id
        records.append(
            unify_record(
                work,
                tier=1,
                match_reason="orcid_claimed",
                orcid=orcid,
                source_name="orcid",
            )
        )
    return records
