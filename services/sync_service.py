"""External publication sync service (ORCID-anchored tiered pipeline)."""
import requests

from services import arxiv_client, crossref_client, sync_log_service
from services import match_candidate_service, member_service, publication_service
from services.pipeline import runner as pipeline_runner
from services.pipeline.records import to_import_candidate


def sync_from_orcid(member_id):
    """Fetch Tier 1 ORCID works and import them for a lab member."""
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
        result = _run_pipeline_for_member(member, stages=("orcid",))
        return _finish(log, result["status"], result["message"], result)
    except requests.RequestException as exc:
        return _finish(log, "error", f"ORCID API request failed: {exc}")
    except Exception as exc:
        return _finish(log, "error", f"ORCID sync failed: {exc}")


def sync_from_openalex(member_id):
    """Fetch Tier 2 OpenAlex works by ORCID (not Author ID) and import them."""
    log = sync_log_service.start_log("openalex")
    member = member_service.get_member_by_id(member_id)
    if not member:
        return _finish(log, "error", f"Member {member_id} not found.")
    if not member.orcid:
        return _finish(
            log,
            "error",
            f"Member '{member.name}' needs an ORCID for OpenAlex sync "
            "(Author ID is not used as the sync anchor).",
        )

    try:
        result = _run_pipeline_for_member(member, stages=("openalex",))
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
    """
    Enrich/import from arXiv by ID or explicit fielded query.

    Author-name search is not used for member auto-sync. Prefer id:NNNN.NNNNN.
    """
    log = sync_log_service.start_log("arxiv")
    query = (query or "").strip()
    if not query:
        return _finish(log, "error", "Search query is required (prefer id:NNNN.NNNNN).")

    member = member_service.get_member_by_id(member_id) if member_id else None

    try:
        result = _sync_arxiv_query(query, member)
        return _finish(log, result["status"], result["message"], result)
    except requests.RequestException as exc:
        return _finish(log, "error", f"arXiv API request failed: {exc}")
    except Exception as exc:
        return _finish(log, "error", f"arXiv sync failed: {exc}")


def sync_from_arxiv_for_member(member_id, max_results=50):
    """
    Member arXiv path no longer searches by author name.

    Preprints arrive via ORCID/OpenAlex ORCID queries; arXiv is ID enrichment only.
    """
    member = member_service.get_member_by_id(member_id)
    if not member:
        return _skipped_result("arxiv", f"Member {member_id} not found.")
    return _skipped_result(
        "arxiv",
        (
            f"arXiv name search disabled for {member.name}. "
            "Preprints are imported via ORCID/OpenAlex ORCID filters; "
            "use Sync Tools with an arXiv id: query for ID enrichment only."
        ),
    )


def sync_member_publications(member_id):
    """
    ORCID-anchored sync for one member.

    Tier 1 (ORCID) + Tier 2 (OpenAlex-by-ORCID) auto-import.
    Tier 3 name-only candidates are scored into the review queue only.
    Blocklist always wins. Then Crossref enrichment runs for DOI metadata.
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

    if not member.orcid:
        sources["pipeline"] = _skipped_result(
            "pipeline",
            "No ORCID configured — ORCID is required for identity-safe sync.",
        )
        sources["crossref"] = _skipped_result("crossref", "Skipped without ORCID sync.")
        totals = _aggregate_source_results(sources.values())
        return {
            "member_id": member.id,
            "member_name": member.name,
            "status": "skipped",
            "message": format_member_sync_message(member.name, totals, sources),
            "sources": sources,
            **totals,
        }

    try:
        pipeline_result = _run_pipeline_for_member(member)
        sources["pipeline"] = pipeline_result
    except requests.RequestException as exc:
        sources["pipeline"] = {
            "status": "error",
            "source": "pipeline",
            "message": f"Pipeline API request failed: {exc}",
            "created": 0,
            "updated": 0,
            "skipped": 0,
        }
    except Exception as exc:
        sources["pipeline"] = {
            "status": "error",
            "source": "pipeline",
            "message": f"Pipeline sync failed: {exc}",
            "created": 0,
            "updated": 0,
            "skipped": 0,
        }

    sources["crossref"] = _enrich_member_publications_from_crossref(member)

    totals = _aggregate_source_results(sources.values())
    status = _overall_status(sources.values())
    message = format_member_sync_message(member.name, totals, sources)

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
        ("pipeline", "ORCID/OpenAlex pipeline"),
        ("orcid", "ORCID"),
        ("openalex", "OpenAlex"),
        ("arxiv", "arXiv"),
        ("crossref", "Crossref"),
    ):
        result = sources.get(key) or {}
        if not result:
            continue
        status = result.get("status")
        if status == "skipped":
            source_notes.append(f"{label} skipped ({result.get('message', 'not configured')})")
        elif status == "success":
            extra = []
            if result.get("review_queued"):
                extra.append(f"{result['review_queued']} queued for review")
            if result.get("blocked"):
                extra.append(f"{result['blocked']} blocked")
            suffix = f" ({'; '.join(extra)})" if extra else ""
            source_notes.append(
                f"{label}: +{result.get('created', 0)} new, "
                f"{result.get('updated', 0)} updated{suffix}"
            )
        elif status == "error":
            detail = (result.get("message") or "").strip()
            if detail:
                short = detail if len(detail) <= 120 else detail[:117] + "..."
                source_notes.append(f"{label} failed ({short})")
            else:
                source_notes.append(f"{label} failed")

    if source_notes:
        parts.append("Sources: " + "; ".join(source_notes) + ".")
    return " ".join(parts)


def sync_all_members(active_only=True):
    """Sync publications for all registered lab members via the ORCID pipeline."""
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


def _run_pipeline_for_member(member, stages=None):
    """
    Run the tiered matcher and write accepted papers + review queue.

    stages is reserved for future partial runs; currently always full ORCID+OpenAlex.
    """
    lab_names = [item.name for item in member_service.get_all_members()]
    result = pipeline_runner.run_for_member(member, lab_member_names=lab_names)

    import_candidates = [
        to_import_candidate(record) for record in result.get("accepted") or []
    ]
    summary = _import_candidates(import_candidates, member)

    review_stats = match_candidate_service.upsert_review_candidates(
        member.id, result.get("needs_review") or []
    )

    blocked = sum(
        1 for item in result.get("decisions_log") or [] if item.get("reason") == "manual_blocklist"
    )
    accepted_count = len(result.get("accepted") or [])
    review_count = len(result.get("needs_review") or [])

    # Optionally refresh observed OpenAlex author ID for coverage display only.
    observed = result.get("observed_openalex_author_ids") or []
    if observed and not member.openalex_author_id:
        member.openalex_author_id = observed[0]
        from database.db import db

        db.session.commit()

    message = (
        f"Pipeline for {member.name}: {accepted_count} accepted (Tier 1/2/allowlist), "
        f"{review_count} queued for Tier 3 review, {blocked} blocked; "
        f"created {summary['created']}, updated {summary['updated']}, "
        f"skipped {summary['skipped']}; review upsert "
        f"+{review_stats['created']}/~{review_stats['updated']}."
    )
    return {
        "status": "success",
        "source": "pipeline",
        "message": message,
        "review_queued": review_count,
        "blocked": blocked,
        "decisions_log": result.get("decisions_log") or [],
        "observed_openalex_author_ids": observed,
        **summary,
    }


def _sync_arxiv_query(query, member=None, max_results=25, filter_for_member=False):
    """Manual arXiv import — prefer ID queries; name search is not identity-safe."""
    candidates = arxiv_client.fetch_works(query, max_results=max_results)
    # Do not auto-trust name hits for members; only import when an explicit query
    # was provided by an admin (ID enrichment or deliberate search).
    summary = _import_candidates(candidates, member)
    label = member.name if member else query
    message = (
        f"arXiv sync for {label}: fetched {len(candidates)} results; "
        f"created {summary['created']}, updated {summary['updated']}, "
        f"skipped {summary['skipped']}."
    )
    if query.lower().startswith("au:"):
        message += " Warning: author-name arXiv queries are not identity-safe."
    return {"status": "success", "message": message, **summary}


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
