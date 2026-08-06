"""
Tier 2: OpenAlex works filtered by ORCID.

IMPORTANT: Do not anchor sync on OpenAlex Author IDs. OpenAlex suffers from
split/merge problems (one person → many IDs; occasionally two people → one ID).
Always query works by authorship ORCID and re-verify the ORCID on each work
before accepting. Observed author IDs may be collected for coverage only.
"""
from services import openalex_client
from services.orcid_client import normalize_orcid
from services.pipeline.normalize import unify_record


def fetch_tier2_works(orcid):
    """
    Fetch OpenAlex works for an ORCID and return unified Tier 2 records.

    Rejects any work whose authorships do not include the matching ORCID.
    """
    orcid = normalize_orcid(orcid)
    if not orcid:
        return [], []

    raw_works, observed_author_ids = openalex_client.fetch_works_by_orcid(orcid)
    records = []
    for work in raw_works:
        # Client already filters; re-verify authorship ORCID before accepting.
        if not openalex_client.work_has_orcid(
            work.get("_raw_authorships") or [], orcid
        ):
            continue
        records.append(
            unify_record(
                work,
                tier=2,
                match_reason="orcid_in_authorship",
                orcid=orcid,
                source_name="openalex",
            )
        )
    return records, observed_author_ids
