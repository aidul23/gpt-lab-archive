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
    """Allowlist + import publication; mark candidate approved."""
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
    db.session.commit()
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
    query = PublicationMatchCandidate.query.filter_by(
        member_id=member_id, status=STATUS_PENDING
    )
    doi = (record.get("doi") or "").strip().lower()
    arxiv_id = (record.get("arxiv_id") or "").strip().lower()
    if doi:
        found = query.filter(db.func.lower(PublicationMatchCandidate.doi) == doi).first()
        if found:
            return found
    if arxiv_id:
        found = query.filter(
            db.func.lower(PublicationMatchCandidate.arxiv_id) == arxiv_id
        ).first()
        if found:
            return found
    title = (record.get("title") or "").strip().lower()
    year = record.get("year")
    if title:
        candidates = query.all()
        for item in candidates:
            if (item.title or "").strip().lower() == title and item.year == year:
                return item
    return None
