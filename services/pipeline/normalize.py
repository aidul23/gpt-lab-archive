"""Normalize and merge metadata across ORCID / OpenAlex / arXiv records."""
from services.api_client_utils import normalize_doi
from services.identity_verification import normalize_arxiv_id
from services.pipeline.records import author_names, empty_record


def normalize_title(title):
    """Lowercase, strip punctuation, collapse whitespace."""
    import re

    if not title:
        return ""
    text = title.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def unify_record(raw, *, tier, match_reason, orcid=None, source_name=None):
    """Build a unified pipeline record from a source-specific candidate."""
    record = empty_record()
    record["title"] = (raw.get("title") or "").strip() or None
    record["authors"] = list(raw.get("authors") or [])
    record["year"] = raw.get("year")
    record["doi"] = normalize_doi(raw.get("doi"))
    arxiv_id = normalize_arxiv_id(raw.get("arxiv_id"))
    if not arxiv_id and (raw.get("source") or "").lower() == "arxiv":
        arxiv_id = normalize_arxiv_id(raw.get("source_id"))
    if not arxiv_id:
        arxiv_id = normalize_arxiv_id(raw.get("url")) or normalize_arxiv_id(raw.get("doi"))
    record["arxiv_id"] = arxiv_id
    record["venue"] = raw.get("venue")
    record["type"] = raw.get("type") or "article"
    record["url"] = raw.get("url")
    record["pdf_url"] = raw.get("pdf_url")
    record["abstract"] = raw.get("abstract")
    record["publication_date"] = raw.get("publication_date")
    record["source"] = raw.get("source")
    record["source_id"] = raw.get("source_id")
    record["is_preprint"] = bool(raw.get("is_preprint"))
    record["is_published"] = bool(raw.get("is_published", not record["is_preprint"]))
    record["confidence_tier"] = tier
    record["match_reason"] = match_reason
    record["sources"] = [source_name or raw.get("source") or "unknown"]
    if orcid:
        record["matched_researcher_orcids"] = [orcid]
    record["concepts"] = list(raw.get("concepts") or [])
    record["affiliations"] = list(raw.get("affiliations") or [])
    record["openalex_author_ids"] = list(raw.get("openalex_author_ids") or [])
    return record


def merge_records(primary, secondary):
    """
    Merge two records for the same work.

    Keeps the richest metadata and unions sources / IDs / concepts.
    Prefer lower confidence_tier number (Tier 1 over Tier 2 over Tier 3).
    """
    if not primary:
        return secondary
    if not secondary:
        return primary

    merged = dict(primary)
    for key in (
        "title",
        "abstract",
        "year",
        "publication_date",
        "venue",
        "type",
        "url",
        "pdf_url",
        "doi",
        "arxiv_id",
        "source",
        "source_id",
    ):
        if not merged.get(key) and secondary.get(key):
            merged[key] = secondary[key]

    if len(author_names(secondary)) > len(author_names(merged)):
        merged["authors"] = list(secondary.get("authors") or [])

    merged["is_preprint"] = bool(merged.get("is_preprint") or secondary.get("is_preprint"))
    merged["is_published"] = not merged["is_preprint"] if merged.get("is_preprint") else bool(
        merged.get("is_published") or secondary.get("is_published")
    )

    primary_tier = merged.get("confidence_tier")
    secondary_tier = secondary.get("confidence_tier")
    if primary_tier is None:
        merged["confidence_tier"] = secondary_tier
        merged["match_reason"] = secondary.get("match_reason")
    elif secondary_tier is not None and secondary_tier < primary_tier:
        merged["confidence_tier"] = secondary_tier
        merged["match_reason"] = secondary.get("match_reason")

    merged["sources"] = sorted(
        set((merged.get("sources") or []) + (secondary.get("sources") or []))
    )
    merged["matched_researcher_orcids"] = sorted(
        set(
            (merged.get("matched_researcher_orcids") or [])
            + (secondary.get("matched_researcher_orcids") or [])
        )
    )
    merged["concepts"] = _unique_preserve(
        (merged.get("concepts") or []) + (secondary.get("concepts") or [])
    )
    merged["affiliations"] = _unique_preserve(
        (merged.get("affiliations") or []) + (secondary.get("affiliations") or [])
    )
    merged["openalex_author_ids"] = sorted(
        set(
            (merged.get("openalex_author_ids") or [])
            + (secondary.get("openalex_author_ids") or [])
        )
    )

    if secondary.get("doi") and not merged.get("doi"):
        merged["doi"] = secondary["doi"]
    if secondary.get("arxiv_id") and not merged.get("arxiv_id"):
        merged["arxiv_id"] = secondary["arxiv_id"]

    return merged


def _unique_preserve(values):
    seen = set()
    result = []
    for value in values:
        key = value if not isinstance(value, dict) else tuple(sorted(value.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
