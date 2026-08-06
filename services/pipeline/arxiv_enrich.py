"""Safe arXiv enrichment by ID only (never by author name)."""
from services import arxiv_client
from services.identity_verification import normalize_arxiv_id
from services.pipeline.normalize import merge_records, unify_record


def enrich_records_with_arxiv(records):
    """
    For records that already have an arXiv ID, fetch metadata by ID and merge.

    This is an ID lookup, not a name search, and is safe for auto pipelines.
    """
    enriched = []
    for record in records or []:
        arxiv_id = normalize_arxiv_id(record.get("arxiv_id"))
        if not arxiv_id:
            enriched.append(record)
            continue
        try:
            raw = arxiv_client.fetch_by_id(arxiv_id)
        except Exception:
            enriched.append(record)
            continue
        if not raw:
            enriched.append(record)
            continue
        arxiv_record = unify_record(
            raw,
            tier=record.get("confidence_tier") or 2,
            match_reason=record.get("match_reason") or "arxiv_id_enrichment",
            orcid=(record.get("matched_researcher_orcids") or [None])[0],
            source_name="arxiv",
        )
        enriched.append(merge_records(record, arxiv_record))
    return enriched
