"""Member-related database operations."""
from database.db import Member, Publication, PublicationAuthor, db, utcnow
from services import upload_service
from services.member_hierarchy import (
    MEMBER_ROLES,
    build_hierarchy,
    normalize_role,
    parse_reports_to_id,
    would_create_cycle,
)


APPROVAL_APPROVED = "approved"
APPROVAL_PENDING = "pending"
APPROVAL_REJECTED = "rejected"


def get_all_members(include_inactive=False, public_only=True):
    """Return lab members ordered by name."""
    query = Member.query
    if public_only:
        query = query.filter_by(approval_status=APPROVAL_APPROVED)
    if not include_inactive:
        query = query.filter_by(active=True)
    return query.order_by(Member.name).all()


def get_all_members_admin():
    """Return all members for admin views."""
    return Member.query.order_by(Member.name).all()


def get_pending_members():
    """Return member profiles waiting for admin approval."""
    return (
        Member.query.filter_by(approval_status=APPROVAL_PENDING)
        .order_by(Member.submitted_at.desc(), Member.name)
        .all()
    )


def get_member_by_id(member_id):
    """Return a single member or None."""
    return Member.query.get(member_id)


def get_public_member(member_id):
    """Return a member only if their profile is publicly visible."""
    member = get_member_by_id(member_id)
    if member and member.is_publicly_visible():
        return member
    return None


def count_members(include_inactive=False, public_only=True):
    """Count lab members."""
    query = Member.query
    if public_only:
        query = query.filter_by(approval_status=APPROVAL_APPROVED)
    if not include_inactive:
        query = query.filter_by(active=True)
    return query.count()


def count_pending_members():
    """Count member profiles awaiting admin approval."""
    return Member.query.filter_by(approval_status=APPROVAL_PENDING).count()


def create_member_admin(data, photo_file=None):
    """Create a member directly from the admin panel."""
    member = Member(
        name=data.get("name", "").strip(),
        role=_resolve_role(data.get("role")),
        email=_optional_text(data.get("email")),
        orcid=_optional_text(data.get("orcid")),
        openalex_author_id=_optional_text(data.get("openalex_author_id")),
        profile_url=_optional_text(data.get("profile_url")),
        bio=_optional_text(data.get("bio")),
        active=_parse_bool(data.get("active"), default=True),
        approval_status=APPROVAL_APPROVED,
        is_self_registered=False,
        reviewed_at=utcnow(),
    )
    db.session.add(member)
    db.session.flush()
    member.reports_to_id = _resolve_reports_to(data.get("reports_to_id"), member.id)
    _save_photo(member, photo_file)
    db.session.commit()
    return member


def submit_member_registration(data, photo_file=None):
    """Create a pending member profile submitted by a lab member."""
    member = Member(
        name=data.get("name", "").strip(),
        role=_resolve_role(data.get("role")),
        email=_optional_text(data.get("email")),
        orcid=_optional_text(data.get("orcid")),
        openalex_author_id=_optional_text(data.get("openalex_author_id")),
        profile_url=_optional_text(data.get("profile_url")),
        bio=_optional_text(data.get("bio")),
        active=True,
        approval_status=APPROVAL_PENDING,
        is_self_registered=True,
        submitted_at=utcnow(),
    )
    db.session.add(member)
    db.session.flush()
    member.reports_to_id = _resolve_reports_to(data.get("reports_to_id"), member.id)
    _save_photo(member, photo_file)
    db.session.commit()
    return member


def update_member(member, data, photo_file=None):
    """Update an existing lab member."""
    member.name = data.get("name", member.name).strip()
    member.role = _resolve_role(data.get("role"))
    member.email = _optional_text(data.get("email"))
    member.orcid = _optional_text(data.get("orcid"))
    member.openalex_author_id = _optional_text(data.get("openalex_author_id"))
    member.profile_url = _optional_text(data.get("profile_url"))
    member.bio = _optional_text(data.get("bio"))
    member.active = _parse_bool(data.get("active"), default=member.active)
    member.reports_to_id = _resolve_reports_to(data.get("reports_to_id"), member.id)
    _save_photo(member, photo_file)
    db.session.commit()
    return member


def get_supervisor_choices(exclude_member_id=None):
    """Active members that can appear in the Reports to selector."""
    members = get_all_members(include_inactive=False, public_only=True)
    if exclude_member_id:
        members = [item for item in members if item.id != exclude_member_id]
    return sorted(
        members,
        key=lambda item: (
            role_sort_key(item.role),
            (item.name or "").casefold(),
        ),
    )


def get_members_hierarchy(include_inactive=False, public_only=True):
    """Return hierarchy forest for the public members page."""
    members = get_all_members(
        include_inactive=include_inactive,
        public_only=public_only,
    )
    return build_hierarchy(members)


def role_choices():
    """Role options for forms."""
    return list(MEMBER_ROLES)


def role_sort_key(role):
    from services.member_hierarchy import role_rank

    return role_rank(role)


def approve_member(member):
    """Approve a pending member profile."""
    member.approval_status = APPROVAL_APPROVED
    member.active = True
    member.reviewed_at = utcnow()
    db.session.commit()
    return member


def reject_member(member):
    """Reject a pending member profile."""
    member.approval_status = APPROVAL_REJECTED
    member.active = False
    member.reviewed_at = utcnow()
    db.session.commit()
    return member


def count_linked_publications(member_id):
    """Count publications linked to a member."""
    return (
        db.session.query(PublicationAuthor.publication_id)
        .filter(PublicationAuthor.member_id == member_id)
        .distinct()
        .count()
    )


def get_linked_publications(member_id):
    """Return publications linked to a member."""
    return (
        Publication.query.join(PublicationAuthor)
        .filter(PublicationAuthor.member_id == member_id)
        .order_by(Publication.year.desc(), Publication.title)
        .all()
    )


def delete_member_with_publications(member_id):
    """
    Delete a member and all publications they are linked to.

    Returns a summary dict, or None if the member does not exist.
    """
    member = Member.query.get(member_id)
    if not member:
        return None

    member_name = member.name
    publications = get_linked_publications(member_id)
    publication_count = len(publications)

    # Detach direct reports so FK does not block delete.
    Member.query.filter_by(reports_to_id=member_id).update(
        {Member.reports_to_id: None},
        synchronize_session=False,
    )

    for publication in publications:
        db.session.delete(publication)

    upload_service.delete_member_photo(member)
    db.session.delete(member)
    db.session.commit()

    return {
        "member_name": member_name,
        "publications_deleted": publication_count,
    }


def get_member_profile_summary(member_id):
    """Return publication stats and themes for a member profile page."""
    from services import publication_service

    publications = publication_service.get_publications_for_member(member_id)
    preprint_count = sum(1 for publication in publications if publication.is_preprint)
    themes = {}
    years = []

    for publication in publications:
        if publication.year:
            years.append(publication.year)
        for theme in publication.tags_by_kind("theme"):
            themes[theme.id] = theme

    return {
        "publication_count": len(publications),
        "preprint_count": preprint_count,
        "published_count": len(publications) - preprint_count,
        "themes": sorted(themes.values(), key=lambda theme: theme.name),
        "first_year": min(years) if years else None,
        "latest_year": max(years) if years else None,
    }


def _save_photo(member, photo_file):
    """Save an uploaded photo if provided."""
    if photo_file and photo_file.filename:
        upload_service.save_member_photo(member, photo_file)


def _resolve_role(value):
    """Prefer canonical role labels; keep unknown custom text as fallback."""
    text = _optional_text(value)
    if not text:
        return None
    return normalize_role(text) or text


def _resolve_reports_to(value, member_id=None):
    """Validate and return reports_to_id, or raise ValueError."""
    reports_to_id = parse_reports_to_id(value)
    if not reports_to_id:
        return None

    supervisor = get_member_by_id(reports_to_id)
    if not supervisor or not supervisor.active:
        raise ValueError("Selected supervisor was not found.")

    members_by_id = {item.id: item for item in Member.query.all()}
    if would_create_cycle(member_id, reports_to_id, members_by_id):
        raise ValueError("A member cannot report to themselves or create a reporting loop.")
    return reports_to_id


def _optional_text(value):
    """Normalize optional text fields."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _parse_bool(value, default=False):
    """Parse checkbox / form boolean values."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "on", "yes"}
