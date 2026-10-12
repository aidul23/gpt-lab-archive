"""Admin review queue for Tier 3 match candidates."""
import json

from database.db import PublicationMatchCandidate, db, utcnow
from services import publication_service
from services.pipeline.overrides import allow_record_for_member, block_record_for_member
from services.pipeline.records import author_names, to_import_candidate


STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


def get_candidate_by_id(candidate_id):
    return PublicationMatchCandidate.query.get(candidate_id)


def get_pending_candidates():
    return (
        PublicationMatchCandidate.query.filter_by(status=STATUS_PENDING)
        .order_by(PublicationMatchCandidate.score.desc(), PublicationMatchCandidate.submitted_at.desc())
        .all()
    )


def count_pending_candidates():
    return PublicationMatchCandidate.query.filter_by(status=STATUS_PENDING).count()


def get_recent_candidates(limit=40):
    return (
        PublicationMatchCandidate.query.order_by(PublicationMatchCandidate.submitted_at.desc())
        .limit(limit)
        .all()
    )


def upsert_review_candidates(member_id, records):
    """Insert or refresh pending Tier 3 candidates for a member."""
    created = 0
    updated = 0
    for record in records or []:
        existing = _find_pending(member_id, record)
        payload = json.dumps(record, ensure_ascii=False, default=str)
        authors = author_names(record)
        breakdown = record.get("score_breakdown") or {}
        if existing:
            existing.title = record.get("title") or existing.title
            existing.year = record.get("year")
            existing.doi = record.get("doi")
            existing.arxiv_id = record.get("arxiv_id")
            existing.venue = record.get("venue")
            existing.authors_json = json.dumps(authors, ensure_ascii=False)
            existing.score = record.get("score")
            existing.score_breakdown_json = json.dumps(breakdown, ensure_ascii=False)
            existing.payload_json = payload
            existing.match_reason = record.get("match_reason")
            updated += 1
        else:
            db.session.add(
                PublicationMatchCandidate(
                    member_id=member_id,
                    title=record.get("title") or "Untitled",
                    year=record.get("year"),
                    doi=record.get("doi"),
                    arxiv_id=record.get("arxiv_id"),
                    venue=record.get("venue"),
                    authors_json=json.dumps(authors, ensure_ascii=False),
                    score=record.get("score"),
                    score_breakdown_json=json.dumps(breakdown, ensure_ascii=False),
                    payload_json=payload,
                    status=STATUS_PENDING,
                    match_reason=record.get("match_reason"),
                    submitted_at=utcnow(),
                )
            )
            created += 1
    db.session.commit()
    return {"created": created, "updated": updated}


def approve_candidate(candidate):
    """Allowlist + import publication; mark candidate approved.

    Also links other lab members listed as coauthors on the same paper so
    admin does not need to re-approve the work once per author.
    """
    payload = _payload(candidate)
    allow_record_for_member(
        candidate.member_id,
        payload,
        note=f"Approved match candidate #{candidate.id}",
    )
    import_data = to_import_candidate(payload)
    member = candidate.member
    result = publication_service.import_publication(
        import_data,
        link_member_id=candidate.member_id,
        link_member_name=member.name if member else None,
    )
    candidate.status = STATUS_APPROVED
    candidate.reviewed_at = utcnow()
    candidate.created_publication_id = result.get("publication_id")

    coauthors_linked = []
    publication_id = result.get("publication_id")
    if publication_id:
        publication = publication_service.get_publication_by_id_admin(publication_id)
        if publication:
            coauthors_linked = publication_service.link_matching_lab_coauthors(
                publication,
                payload,
                exclude_member_ids=[candidate.member_id],
            )
            # Same paper may still sit pending for the approving member under
            # another candidate row (e.g. DOI vs arXiv) — clear those too.
            resolve_pending_for_record(
                candidate.member_id,
                payload,
                publication_id=publication_id,
                status=STATUS_APPROVED,
                note=f"Resolved with match candidate #{candidate.id}",
                skip_candidate_id=candidate.id,
            )

    db.session.commit()
    result = dict(result)
    result["coauthors_linked"] = coauthors_linked
    return candidate, result


def reject_candidate(candidate):
    """Blocklist + mark candidate rejected."""
    payload = _payload(candidate)
    block_record_for_member(
        candidate.member_id,
        payload,
        note=f"Rejected match candidate #{candidate.id}",
    )
    candidate.status = STATUS_REJECTED
    candidate.reviewed_at = utcnow()
    db.session.commit()
    return candidate


def resolve_pending_for_record(
    member_id,
    record,
    *,
    publication_id=None,
    status=STATUS_APPROVED,
    note=None,
    skip_candidate_id=None,
):
    """Mark pending Match Review rows for this member+paper as resolved."""
    pending = _find_all_pending(member_id, record)
    updated = 0
    for item in pending:
        if skip_candidate_id and item.id == skip_candidate_id:
            continue
        item.status = status
        item.reviewed_at = utcnow()
        if publication_id and not item.created_publication_id:
            item.created_publication_id = publication_id
        if note and not item.match_reason:
            item.match_reason = note
        updated += 1
    if updated:
        db.session.commit()
    return updated


def authors_list(candidate):
    try:
        return json.loads(candidate.authors_json or "[]")
    except json.JSONDecodeError:
        return []


def breakdown_dict(candidate):
    try:
        return json.loads(candidate.score_breakdown_json or "{}")
    except json.JSONDecodeError:
        return {}


def _payload(candidate):
    try:
        payload = json.loads(candidate.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not payload:
        payload = {
            "title": candidate.title,
            "year": candidate.year,
            "doi": candidate.doi,
            "arxiv_id": candidate.arxiv_id,
            "venue": candidate.venue,
            "authors": authors_list(candidate),
            "match_reason": candidate.match_reason or "manual_allowlist",
            "confidence_tier": 2,
            "sources": ["manual_review"],
        }
    return payload


def _find_pending(member_id, record):
    found = _find_all_pending(member_id, record)
    return found[0] if found else None


def _find_all_pending(member_id, record):
    """Return all pending candidates for member that match DOI / arXiv / title+year."""
    query = PublicationMatchCandidate.query.filter_by(
        member_id=member_id, status=STATUS_PENDING
    )
    doi = (record.get("doi") or "").strip().lower()
    arxiv_id = (record.get("arxiv_id") or "").strip().lower()
    title = (record.get("title") or "").strip().lower()
    year = record.get("year")

    matches = []
    seen_ids = set()

    def _add(rows):
        for item in rows:
            if item.id in seen_ids:
                continue
            seen_ids.add(item.id)
            matches.append(item)

    if doi:
        _add(query.filter(db.func.lower(PublicationMatchCandidate.doi) == doi).all())
    if arxiv_id:
        _add(
            query.filter(
                db.func.lower(PublicationMatchCandidate.arxiv_id) == arxiv_id
            ).all()
        )
    if title:
        for item in query.all():
            if (item.title or "").strip().lower() == title and (
                year is None or item.year == year
            ):
                _add([item])
    return matches
