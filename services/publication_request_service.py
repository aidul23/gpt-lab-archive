"""Member requests to add missing publications."""
from database.db import PublicationRequest, db, utcnow
from services import member_service, publication_service


STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


def get_request_by_id(request_id):
    """Return a publication request or None."""
    return PublicationRequest.query.get(request_id)


def get_pending_requests():
    """Return pending requests newest first."""
    return (
        PublicationRequest.query.filter_by(status=STATUS_PENDING)
        .order_by(PublicationRequest.submitted_at.desc())
        .all()
    )


def get_all_requests(limit=100):
    """Return recent requests for admin review."""
    return (
        PublicationRequest.query.order_by(PublicationRequest.submitted_at.desc())
        .limit(limit)
        .all()
    )


def count_pending_requests():
    """Count requests waiting for admin review."""
    return PublicationRequest.query.filter_by(status=STATUS_PENDING).count()


def submit_request(form):
    """
    Create a pending publication request from a public form.

    Raises ValueError for validation errors.
    """
    title = (form.get("title") or "").strip()
    if not title:
        raise ValueError("Title is required.")

    member_id = _parse_int(form.get("member_id"))
    if not member_id:
        raise ValueError("Please select your member profile.")

    member = member_service.get_public_member(member_id)
    if not member:
        raise ValueError("Selected member profile was not found.")

    request_row = PublicationRequest(
        member_id=member.id,
        requester_email=_optional_text(form.get("requester_email")),
        title=title,
        year=_parse_int(form.get("year")),
        doi=_optional_text(form.get("doi")),
        url=_optional_text(form.get("url")),
        venue=_optional_text(form.get("venue")),
        authors_text=_optional_text(form.get("authors_text")),
        notes=_optional_text(form.get("notes")),
        status=STATUS_PENDING,
        submitted_at=utcnow(),
    )
    db.session.add(request_row)
    db.session.commit()
    return request_row


def reject_request(request_row):
    """Mark a request as rejected."""
    request_row.status = STATUS_REJECTED
    request_row.reviewed_at = utcnow()
    db.session.commit()
    return request_row


def approve_request(request_row):
    """
    Create a publication from the request, link the member, and mark approved.

    Returns (request_row, publication).
    """
    member = member_service.get_member_by_id(request_row.member_id)
    if not member:
        raise ValueError("Linked member no longer exists.")

    authors_data = _authors_from_request(request_row, member)
    data = {
        "title": request_row.title,
        "year": request_row.year,
        "doi": request_row.doi,
        "url": request_row.url,
        "venue": request_row.venue,
        "source": "member_request",
        "is_preprint": False,
        "is_published": True,
        "is_visible": True,
    }
    publication = publication_service.create_publication(data, authors_data)
    request_row.status = STATUS_APPROVED
    request_row.reviewed_at = utcnow()
    request_row.created_publication_id = publication.id
    db.session.commit()
    return request_row, publication


def _authors_from_request(request_row, member):
    """Build author rows from free-text authors, ensuring the member is linked."""
    authors_data = []
    raw = (request_row.authors_text or "").strip()
    if raw:
        parts = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
        for index, name in enumerate(parts, start=1):
            authors_data.append(
                {
                    "author_name": name,
                    "member_id": member.id
                    if name.lower() == member.name.strip().lower()
                    else None,
                    "author_position": index,
                }
            )

    linked = any(author.get("member_id") == member.id for author in authors_data)
    if not linked:
        authors_data.insert(
            0,
            {
                "author_name": member.name,
                "member_id": member.id,
                "author_position": 1,
            },
        )
        for index, author in enumerate(authors_data, start=1):
            author["author_position"] = index

    return authors_data


def _optional_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _parse_int(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
