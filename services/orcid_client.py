"""ORCID public API client."""
import re

from services.api_client_utils import get_json, map_work_type, normalize_doi, parse_year
from services.identity_verification import normalize_arxiv_id


def normalize_orcid(orcid):
    """Return a bare ORCID identifier."""
    if not orcid:
        return None
    orcid = str(orcid).strip()
    orcid = re.sub(r"^https?://orcid\.org/", "", orcid, flags=re.IGNORECASE)
    return orcid or None


def orcid_url(orcid):
    """Return the canonical https://orcid.org/{id} form."""
    bare = normalize_orcid(orcid)
    if not bare:
        return None
    return f"https://orcid.org/{bare}"


def fetch_works(orcid, extract_all_external_ids=False):
    """Fetch and normalize works for an ORCID profile."""
    orcid = normalize_orcid(orcid)
    if not orcid:
        return []

    url = f"https://pub.orcid.org/v3.0/{orcid}/works"
    payload = get_json(url, "orcid-sync")
    candidates = []

    for group in payload.get("group", []):
        summaries = group.get("work-summary") or []
        if not summaries:
            continue

        work = summaries[0]
        title_block = work.get("title") or {}
        title = ((title_block.get("title") or {}).get("value") or "").strip()
        if not title:
            continue

        external_ids = _extract_external_ids(
            (work.get("external-ids") or {}).get("external-id") or []
        )
        doi = external_ids.get("doi")
        arxiv_id = external_ids.get("arxiv")

        pub_date = work.get("publication-date") or {}
        year = parse_year((pub_date.get("year") or {}).get("value"))
        month = (pub_date.get("month") or {}).get("value")
        day = (pub_date.get("day") or {}).get("value")
        publication_date = _build_date(year, month, day)
        work_type = map_work_type(work.get("type"))
        put_code = work.get("put-code")
        url_value = ((work.get("url") or {}).get("value") or "").strip() or None
        venue = ((work.get("journal-title") or {}).get("value") or "").strip() or None
        raw_type = (work.get("type") or "").lower()
        is_preprint = _is_orcid_preprint(raw_type, venue, url_value, arxiv_id)

        if not arxiv_id:
            arxiv_id = normalize_arxiv_id(url_value) or normalize_arxiv_id(doi)

        candidate = {
            "title": title,
            "abstract": None,
            "year": year,
            "publication_date": publication_date,
            "type": work_type,
            "venue": venue,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "url": url_value or (f"https://doi.org/{doi}" if doi else None),
            "pdf_url": None,
            "source": "orcid",
            "source_id": str(put_code) if put_code is not None else None,
            "is_preprint": is_preprint,
            "is_published": not is_preprint,
            "authors": [],
        }
        if extract_all_external_ids:
            candidate["external_ids"] = external_ids
        candidates.append(candidate)

    return candidates


def _extract_external_ids(external_id_list):
    """Extract DOI, arXiv, and other useful external identifiers."""
    result = {"doi": None, "arxiv": None, "other": []}
    for external_id in external_id_list:
        id_type = (external_id.get("external-id-type") or "").lower().strip()
        value = (external_id.get("external-id-value") or "").strip()
        if not value:
            continue
        if id_type == "doi" and not result["doi"]:
            result["doi"] = normalize_doi(value)
        elif id_type in {"arxiv", "arxiv identifier", "eprint"} and not result["arxiv"]:
            result["arxiv"] = normalize_arxiv_id(value) or value
        else:
            arxiv_guess = normalize_arxiv_id(value)
            if arxiv_guess and not result["arxiv"]:
                result["arxiv"] = arxiv_guess
            result["other"].append({"type": id_type, "value": value})
    return result


def _build_date(year, month, day):
    """Build a YYYY-MM-DD string when possible."""
    if not year:
        return None
    month = str(month or "01").zfill(2)
    day = str(day or "01").zfill(2)
    return f"{year}-{month}-{day}"


def _is_orcid_preprint(raw_type, venue, url_value, arxiv_id=None):
    """Detect whether an ORCID work is a preprint."""
    if arxiv_id:
        return True
    haystack = " ".join(
        part for part in (raw_type, (venue or "").lower(), (url_value or "").lower()) if part
    )
    preprint_tokens = ("preprint", "manuscript", "working-paper", "working paper", "submitted")
    repository_tokens = ("arxiv", "biorxiv", "chemrxiv", "medrxiv", "ssrn", "preprints.org")
    return any(token in haystack for token in preprint_tokens + repository_tokens)
