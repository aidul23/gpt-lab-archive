"""External publication sync service."""
import re

import requests

from services import arxiv_client, crossref_client, openalex_client, orcid_client, sync_log_service
from services import member_service, publication_service


def sync_from_orcid(member_id):
    """Fetch works from ORCID and import them for a lab member."""
    log = sync_log_service.start_log("orcid")
    member = member_service.get_member_by_id(member_id)
    if not member:
        return _finish(log, "error", f"Member {member_id} not found.")
    if not member.orcid:
        return _finish(
            log,
            "error",
            f"Member '{member.name}' does not have an ORCID ID configured.",
        )

    try:
        result = _sync_orcid_for_member(member)
        return _finish(log, result["status"], result["message"], result)
    except requests.RequestException as exc:
        return _finish(log, "error", f"ORCID API request failed: {exc}")
    except Exception as exc:
        return _finish(log, "error", f"ORCID sync failed: {exc}")


def sync_from_openalex(member_id):
    """Fetch works from OpenAlex and import them for a lab member."""
    log = sync_log_service.start_log("openalex")
    member = member_service.get_member_by_id(member_id)
    if not member:
        return _finish(log, "error", f"Member {member_id} not found.")
    if not member.openalex_author_id:
        return _finish(
            log,
            "error",
            f"Member '{member.name}' does not have an OpenAlex author ID configured.",
        )

    try:
        result = _sync_openalex_for_member(member)
        return _finish(log, result["status"], result["message"], result)
    except requests.RequestException as exc:
        return _finish(log, "error", f"OpenAlex API request failed: {exc}")
    except Exception as exc:
        return _finish(log, "error", f"OpenAlex sync failed: {exc}")


def sync_from_crossref(doi):
    """Fetch a publication from Crossref by DOI and import it."""
    log = sync_log_service.start_log("crossref")
    doi = (doi or "").strip()
    if not doi:
        return _finish(log, "error", "DOI is required.")

    try:
        candidate = crossref_client.fetch_work(doi)
        if not candidate:
            return _finish(log, "error", f"No Crossref record found for DOI {doi}.")

        result = publication_service.import_publication(candidate)
        message = (
            f"Crossref sync for DOI {candidate['doi']}: "
            f"{result['action']} '{result['title']}'."
        )
        summary = _summary_from_results([result])
        return _finish(log, "success", message, summary)
    except requests.RequestException as exc:
        return _finish(log, "error", f"Crossref API request failed: {exc}")
    except Exception as exc:
        return _finish(log, "error", f"Crossref sync failed: {exc}")


def sync_from_arxiv(query, member_id=None):
    """Search arXiv and import matching preprints."""
    log = sync_log_service.start_log("arxiv")
    query = (query or "").strip()
    if not query:
        return _finish(log, "error", "Search query is required.")

    member = member_service.get_member_by_id(member_id) if member_id else None

    try:
        result = _sync_arxiv_query(query, member)
        return _finish(log, result["status"], result["message"], result)
    except requests.RequestException as exc:
        return _finish(log, "error", f"arXiv API request failed: {exc}")
    except Exception as exc:
        return _finish(log, "error", f"arXiv sync failed: {exc}")


def sync_from_arxiv_for_member(member_id, max_results=50):
    """Search arXiv for a member's preprints and import matches."""
    member = member_service.get_member_by_id(member_id)
    if not member:
        return _skipped_result("arxiv", f"Member {member_id} not found.")

    queries = _arxiv_author_queries(member.name)
    if not queries:
        return _skipped_result("arxiv", f"Could not build arXiv query for {member.name}.")

    log = sync_log_service.start_log("arxiv")
    try:
        result = _sync_arxiv_queries_for_member(queries, member, max_results=max_results)
        return _finish(log, result["status"], result["message"], result)
    except requests.RequestException as exc:
        return _finish(log, "error", f"arXiv API request failed: {exc}")
    except Exception as exc:
        return _finish(log, "error", f"arXiv sync failed: {exc}")


def _sync_arxiv_queries_for_member(queries, member, max_results=50):
    """Run one or more arXiv author queries and import unique matches."""
    seen_ids = set()
    candidates = []

    for query in queries:
        batch = arxiv_client.fetch_works(query, max_results=max_results)
        batch = _filter_arxiv_for_member(batch, member)
        for candidate in batch:
            source_id = candidate.get("source_id") or candidate.get("title")
            if source_id in seen_ids:
                continue
            seen_ids.add(source_id)
            candidates.append(candidate)
        if candidates:
            break

    # Broader last-name search if precise queries found nothing.
    if not candidates:
        last_name = _member_last_name(member.name)
        broad_query = f"au:{last_name}" if last_name else None
        if broad_query and broad_query not in queries:
            batch = arxiv_client.fetch_works(broad_query, max_results=max_results)
            batch = _filter_arxiv_for_member(batch, member)
            for candidate in batch:
                source_id = candidate.get("source_id") or candidate.get("title")
                if source_id in seen_ids:
                    continue
                seen_ids.add(source_id)
                candidates.append(candidate)

    summary = _import_candidates(candidates, member)
    message = (
        f"arXiv sync for {member.name}: fetched {len(candidates)} matching preprint(s); "
        f"created {summary['created']}, updated {summary['updated']}, "
        f"skipped {summary['skipped']}."
    )
    return {"status": "success", "message": message, **summary}

def sync_member_publications(member_id):
    """
    Sync one member from ORCID, OpenAlex, arXiv, and enrich DOIs via Crossref.

    Returns a structured summary without writing a top-level sync log.
    """
    member = member_service.get_member_by_id(member_id)
    if not member:
        return {
            "member_id": member_id,
            "member_name": None,
            "status": "error",
            "message": f"Member {member_id} not found.",
            "sources": {},
            "created": 0,
            "updated": 0,
            "skipped": 0,
        }

    sources = {}

    if member.orcid:
        sources["orcid"] = sync_from_orcid(member_id)
    else:
        sources["orcid"] = _skipped_result("orcid", "No ORCID configured.")

    if member.openalex_author_id:
        sources["openalex"] = sync_from_openalex(member_id)
    else:
        sources["openalex"] = _skipped_result("openalex", "No OpenAlex author ID configured.")

    sources["arxiv"] = sync_from_arxiv_for_member(member_id)
    sources["crossref"] = _enrich_member_publications_from_crossref(member)

    totals = _aggregate_source_results(sources.values())
    status = _overall_status(sources.values())
    message = format_member_sync_message(
        member.name,
        totals,
        sources,
    )

    return {
        "member_id": member.id,
        "member_name": member.name,
        "status": status,
        "message": message,
        "sources": sources,
        **totals,
    }


def format_member_sync_message(member_name, totals, sources=None):
    """Build a user-friendly sync summary for one member."""
    parts = [
        f"{member_name}: imported {totals['created']} new, updated {totals['updated']}, "
        f"skipped {totals['skipped']} duplicate(s)."
    ]
    if not sources:
        return parts[0]

    source_notes = []
    for key, label in (
        ("orcid", "ORCID"),
        ("openalex", "OpenAlex"),
        ("arxiv", "arXiv preprints"),
        ("crossref", "Crossref"),
    ):
        result = sources.get(key) or {}
        status = result.get("status")
        if status == "skipped":
            source_notes.append(f"{label} skipped ({result.get('message', 'not configured')})")
        elif status == "success":
            source_notes.append(
                f"{label}: +{result.get('created', 0)} new, "
                f"{result.get('updated', 0)} updated"
            )
        elif status == "error":
            detail = (result.get("message") or "").strip()
            if detail:
                # Keep the flash message readable.
                short = detail if len(detail) <= 120 else detail[:117] + "..."
                source_notes.append(f"{label} failed ({short})")
            else:
                source_notes.append(f"{label} failed")

    if source_notes:
        parts.append("Sources: " + "; ".join(source_notes) + ".")
    return " ".join(parts)


def sync_all_members(active_only=True):
    """
    Sync publications and preprints for all registered lab members.

    Uses ORCID, OpenAlex, arXiv, and Crossref enrichment where available.
    """
    log = sync_log_service.start_log("sync_all")
    members = member_service.get_all_members(
        include_inactive=not active_only,
        public_only=True,
    )

    if not members:
        return _finish(log, "success", "No members found to sync.", _empty_summary())

    member_results = []
    combined = _empty_summary()

    for member in members:
        try:
            result = sync_member_publications(member.id)
        except Exception as exc:
            result = {
                "member_id": member.id,
                "member_name": member.name,
                "status": "error",
                "message": str(exc),
                "sources": {},
                "created": 0,
                "updated": 0,
                "skipped": 0,
            }
        member_results.append(result)
        combined["created"] += result.get("created", 0)
        combined["updated"] += result.get("updated", 0)
        combined["skipped"] += result.get("skipped", 0)
        if result.get("status") == "error":
            combined["errors"] += 1

    combined["members_synced"] = len(member_results)
    combined["member_results"] = member_results

    error_count = combined["errors"]
    status = "success" if error_count == 0 else "partial"
    message = (
        f"Automatic sync finished for {len(member_results)} member(s): "
        f"created {combined['created']}, updated {combined['updated']}, "
        f"skipped {combined['skipped']}"
        f"{f', {error_count} error(s)' if error_count else ''}."
    )
    return _finish(log, status, message, combined)


def _sync_orcid_for_member(member):
    candidates = orcid_client.fetch_works(member.orcid)
    summary = _import_candidates(candidates, member)
    message = (
        f"ORCID sync for {member.name}: fetched {len(candidates)} works; "
        f"created {summary['created']}, updated {summary['updated']}, "
        f"skipped {summary['skipped']}."
    )
    return {"status": "success", "message": message, **summary}


def _sync_openalex_for_member(member):
    candidates = openalex_client.fetch_works(member.openalex_author_id)
    summary = _import_candidates(candidates, member)
    message = (
        f"OpenAlex sync for {member.name}: fetched {len(candidates)} works; "
        f"created {summary['created']}, updated {summary['updated']}, "
        f"skipped {summary['skipped']}."
    )
    return {"status": "success", "message": message, **summary}


def _sync_arxiv_query(query, member=None, max_results=25, filter_for_member=False):
    candidates = arxiv_client.fetch_works(query, max_results=max_results)
    if filter_for_member and member:
        candidates = _filter_arxiv_for_member(candidates, member)

    summary = _import_candidates(candidates, member)
    label = member.name if member else query
    message = (
        f"arXiv sync for {label}: fetched {len(candidates)} results; "
        f"created {summary['created']}, updated {summary['updated']}, "
        f"skipped {summary['skipped']}."
    )
    status = "success" if candidates or summary["skipped"] else "success"
    return {"status": status, "message": message, **summary}


def _enrich_member_publications_from_crossref(member):
    """Fill in metadata for a member's publications that have DOIs."""
    publications = publication_service.get_publications_for_member(member.id)
    results = []

    for publication in publications:
        if not publication.doi:
            continue
        try:
            candidate = crossref_client.fetch_work(publication.doi)
            if not candidate:
                continue
            result = publication_service.import_publication(
                candidate,
                link_member_id=member.id,
                link_member_name=member.name,
            )
            results.append(result)
        except requests.RequestException:
            continue

    if not results:
        return _skipped_result(
            "crossref",
            f"No Crossref enrichments applied for {member.name}.",
        )

    summary = _summary_from_results(results)
    message = (
        f"Crossref enrichment for {member.name}: "
        f"created {summary['created']}, updated {summary['updated']}, "
        f"skipped {summary['skipped']}."
    )
    return {"status": "success", "message": message, **summary}


def _filter_arxiv_for_member(candidates, member):
    """Keep arXiv preprints where the member is a listed author."""
    from services.author_matching import names_refer_to_same_person

    filtered = []
    for candidate in candidates:
        for author in candidate.get("authors") or []:
            if names_refer_to_same_person(author.get("author_name"), member.name):
                filtered.append(candidate)
                break
    return filtered


def _author_matches_member(author_name, member):
    """Return True when an author string likely refers to the member."""
    from services.author_matching import names_refer_to_same_person

    return names_refer_to_same_person(author_name, member.name if member else None)


def _arxiv_author_queries(name):
    """
    Build one or more arXiv author search queries from a member name.

    Prefers meaningful given names over prefixes like Md.
    """
    from services.author_matching import last_name, preferred_given_name

    surname = last_name(name)
    if not surname:
        return []

    preferred = preferred_given_name(name)
    queries = []
    if preferred:
        # AND query is more reliable than "Last, First" for arXiv author lists.
        queries.append(f"au:{preferred} AND au:{surname}")
        queries.append(f'au:"{preferred.capitalize()} {surname.capitalize()}"')
    else:
        queries.append(f"au:{surname}")
    return queries


def _arxiv_author_query(name):
    """Build a single targeted arXiv author search query from a member name."""
    queries = _arxiv_author_queries(name)
    return queries[0] if queries else None


def _member_last_name(name):
    """Extract a likely last name from a member display name."""
    from services.author_matching import last_name

    return last_name(name)


def _member_given_name_tokens(name):
    """Extract all given-name tokens."""
    from services.author_matching import given_name_tokens

    return given_name_tokens(name)


def _member_preferred_given_name(name):
    """Prefer a meaningful given name for search."""
    from services.author_matching import preferred_given_name

    return preferred_given_name(name)


def _member_first_name_tokens(name):
    """Backward-compatible alias used by older call sites."""
    return _member_given_name_tokens(name)


def _name_tokens(name):
    """Normalize a person name into lowercase alphanumeric tokens."""
    from services.author_matching import name_tokens

    return name_tokens(name)


# Kept for any older references; leading prefixes live in author_matching.
_NAME_PREFIXES = {
    "md",
    "mohd",
    "abd",
    "abdul",
    "al",
}


def _import_candidates(candidates, member=None):
    """Import a list of normalized publication candidates."""
    results = []
    for candidate in candidates:
        result = publication_service.import_publication(
            candidate,
            link_member_id=member.id if member else None,
            link_member_name=member.name if member else None,
        )
        results.append(result)
    return _summary_from_results(results)


def _summary_from_results(results):
    """Summarize import actions."""
    summary = {"created": 0, "updated": 0, "skipped": 0, "results": results}
    for result in results:
        action = result.get("action", "skipped")
        if action in summary:
            summary[action] += 1
    return summary


def _aggregate_source_results(results):
    """Combine counts from multiple source results."""
    totals = _empty_summary()
    for result in results:
        totals["created"] += result.get("created", 0)
        totals["updated"] += result.get("updated", 0)
        totals["skipped"] += result.get("skipped", 0)
        if result.get("status") == "error":
            totals["errors"] += 1
    return totals


def _overall_status(results):
    """Return success, partial, or skipped depending on source outcomes."""
    statuses = [result.get("status") for result in results]
    if any(status == "error" for status in statuses):
        return "partial"
    if any(status == "success" for status in statuses):
        return "success"
    return "skipped"


def _empty_summary():
    """Return an empty sync summary."""
    return {"created": 0, "updated": 0, "skipped": 0, "errors": 0}


def _skipped_result(source, message):
    """Return a skipped source result without writing a sync log."""
    return {
        "status": "skipped",
        "source": source,
        "message": message,
        "created": 0,
        "updated": 0,
        "skipped": 0,
    }


def _finish(log, status, message, summary=None):
    """Write sync log and return a structured response."""
    sync_log_service.finish_log(log, status, message)
    response = {
        "status": status,
        "source": log.source,
        "message": message,
    }
    if summary is not None:
        response.update(summary)
    return response
