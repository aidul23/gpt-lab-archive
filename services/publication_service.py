"""Publication-related database operations."""
from sqlalchemy import and_, or_

from database.db import Member, Publication, PublicationAuthor, Tag, db


def get_visible_publications_query():
    """Base query for publicly visible publications."""
    return Publication.query.filter_by(is_visible=True)


def count_publications(preprints_only=False, published_only=False):
    """Count visible publications."""
    query = get_visible_publications_query()
    if preprints_only:
        query = query.filter_by(is_preprint=True)
    if published_only:
        query = query.filter_by(is_published=True, is_preprint=False)
    return query.count()


def get_recent_publications(limit=5):
    """Return the most recent visible publications."""
    return (
        get_visible_publications_query()
        .order_by(Publication.year.desc(), Publication.id.desc())
        .limit(limit)
        .all()
    )


def get_publication_by_id(publication_id, include_hidden=False):
    """Return a publication by ID."""
    query = Publication.query
    if not include_hidden:
        query = query.filter_by(is_visible=True)
    return query.filter_by(id=publication_id).first()


def get_publication_by_id_admin(publication_id):
    """Return a publication for admin views (includes hidden)."""
    return Publication.query.get(publication_id)


def get_publications_for_member(member_id):
    """Return visible publications linked to a member, ordered by year."""
    return (
        get_visible_publications_query()
        .join(PublicationAuthor)
        .filter(PublicationAuthor.member_id == member_id)
        .order_by(Publication.year.desc(), Publication.title)
        .all()
    )


def group_publications_by_year(publications):
    """Group publications into a sorted dict keyed by year."""
    grouped = {}
    for publication in publications:
        year = publication.year if publication.year is not None else "Unknown"
        grouped.setdefault(year, []).append(publication)

    def sort_key(item):
        year = item[0]
        if year == "Unknown":
            return -1
        return year

    return dict(sorted(grouped.items(), key=sort_key, reverse=True))


def split_publications_by_status(publications):
    """Split publications into published works and preprints, grouped by year."""
    published = [publication for publication in publications if not publication.is_preprint]
    preprints = [publication for publication in publications if publication.is_preprint]
    return {
        "published": group_publications_by_year(published),
        "preprints": group_publications_by_year(preprints),
    }


def filter_publications(
    year=None,
    pub_type=None,
    member_id=None,
    preprint_status=None,
    search=None,
    tag_id=None,
    theme_id=None,
    preprints_only=False,
    include_hidden=False,
):
    """
    Filter publications with optional query parameters.

    preprint_status: 'preprint', 'published', or None for all.
    """
    query = Publication.query if include_hidden else get_visible_publications_query()

    if preprints_only:
        query = query.filter(Publication.is_preprint.is_(True))

    if year:
        try:
            query = query.filter(Publication.year == int(year))
        except (TypeError, ValueError):
            pass

    if pub_type:
        query = query.filter(Publication.type == pub_type)

    if member_id:
        try:
            member_id = int(member_id)
            query = query.join(PublicationAuthor).filter(
                PublicationAuthor.member_id == member_id
            )
        except (TypeError, ValueError):
            pass

    if preprint_status == "preprint":
        query = query.filter(Publication.is_preprint.is_(True))
    elif preprint_status == "published":
        query = query.filter(Publication.is_preprint.is_(False))

    if tag_id:
        try:
            tag_id = int(tag_id)
            query = query.filter(
                Publication.tags.any(and_(Tag.id == tag_id, Tag.kind == "tag"))
            )
        except (TypeError, ValueError):
            pass

    if theme_id:
        try:
            theme_id = int(theme_id)
            query = query.filter(
                Publication.tags.any(and_(Tag.id == theme_id, Tag.kind == "theme"))
            )
        except (TypeError, ValueError):
            pass

    if search:
        term = f"%{search.strip()}%"
        query = query.outerjoin(PublicationAuthor).filter(
            or_(
                Publication.title.ilike(term),
                Publication.venue.ilike(term),
                Publication.doi.ilike(term),
                PublicationAuthor.author_name.ilike(term),
            )
        ).distinct()

    return query.distinct().order_by(Publication.year.desc(), Publication.title).all()


def get_filter_options():
    """Return distinct years, types, and members for filter dropdowns."""
    years = [
        row[0]
        for row in db.session.query(Publication.year)
        .filter(Publication.is_visible.is_(True), Publication.year.isnot(None))
        .distinct()
        .order_by(Publication.year.desc())
        .all()
    ]
    types = [
        row[0]
        for row in db.session.query(Publication.type)
        .filter(Publication.is_visible.is_(True), Publication.type.isnot(None))
        .distinct()
        .order_by(Publication.type)
        .all()
    ]
    members = Member.query.filter_by(active=True, approval_status="approved").order_by(Member.name).all()
    tags = Tag.query.filter_by(kind="tag").order_by(Tag.name).all()
    themes = Tag.query.filter_by(kind="theme").order_by(Tag.name).all()
    return {"years": years, "types": types, "members": members, "tags": tags, "themes": themes}


def get_all_publications_admin():
    """Return all publications for admin listing."""
    return Publication.query.order_by(Publication.year.desc(), Publication.title).all()


def _parse_int(value):
    """Parse optional integer form values."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _build_publication_from_data(data):
    """Create a Publication object from form data (without authors)."""
    return Publication(
        title=data.get("title", "").strip(),
        abstract=_optional_text(data.get("abstract")),
        year=_parse_int(data.get("year")),
        publication_date=_optional_text(data.get("publication_date")),
        type=_optional_text(data.get("type")),
        venue=_optional_text(data.get("venue")),
        doi=_optional_text(data.get("doi")),
        url=_optional_text(data.get("url")),
        pdf_url=_optional_text(data.get("pdf_url")),
        source=_optional_text(data.get("source")),
        source_id=_optional_text(data.get("source_id")),
        is_preprint=_parse_bool(data.get("is_preprint")),
        is_published=_parse_bool(data.get("is_published"), default=True),
        is_visible=_parse_bool(data.get("is_visible"), default=True),
    )


def _sync_authors(publication, authors_data):
    """
    Replace publication authors from form data.

    authors_data: list of dicts with keys author_name, member_id, author_position
    """
    PublicationAuthor.query.filter_by(publication_id=publication.id).delete()

    prepared = []
    for index, author in enumerate(authors_data, start=1):
        name = (author.get("author_name") or "").strip()
        if not name:
            continue
        prepared.append(
            {
                "author_name": name,
                "member_id": _parse_int(author.get("member_id")),
                "author_position": _parse_int(author.get("author_position")) or index,
            }
        )

    prepared.sort(key=lambda item: item["author_position"])

    for index, author in enumerate(prepared, start=1):
        db.session.add(
            PublicationAuthor(
                publication_id=publication.id,
                member_id=author["member_id"],
                author_name=author["author_name"],
                author_position=index,
            )
        )


def parse_authors_from_form(form):
    """
    Parse repeating author fields from a WTForms-style flat form dict.

    Expected keys:
    - author_name_0, member_id_0, author_position_0
    - author_name_1, member_id_1, author_position_1
    """
    authors = []
    index = 0
    while True:
        name_key = f"author_name_{index}"
        if name_key not in form:
            break
        authors.append(
            {
                "author_name": form.get(name_key),
                "member_id": form.get(f"member_id_{index}"),
                "author_position": form.get(f"author_position_{index}"),
            }
        )
        index += 1

    # Fallback: comma-separated author names with optional member links
    if not authors and form.get("authors_text"):
        names = [name.strip() for name in form.get("authors_text", "").split(",") if name.strip()]
        member_ids = form.getlist("author_member_ids") if hasattr(form, "getlist") else []
        for idx, name in enumerate(names):
            member_id = member_ids[idx] if idx < len(member_ids) else None
            authors.append(
                {
                    "author_name": name,
                    "member_id": member_id,
                    "author_position": idx + 1,
                }
            )

    return authors


def create_publication(data, authors_data, tag_ids=None):
    """Create a publication and its authors."""
    publication = _build_publication_from_data(data)
    db.session.add(publication)
    db.session.flush()
    _sync_authors(publication, authors_data)
    if tag_ids is not None:
        from services import tag_service

        tag_service.set_publication_tags(publication, tag_ids, commit=False)
    db.session.commit()
    return publication


def update_publication(publication, data, authors_data, tag_ids=None):
    """Update a publication and replace its authors."""
    publication.title = data.get("title", publication.title).strip()
    publication.abstract = _optional_text(data.get("abstract"))
    publication.year = _parse_int(data.get("year"))
    publication.publication_date = _optional_text(data.get("publication_date"))
    publication.type = _optional_text(data.get("type"))
    publication.venue = _optional_text(data.get("venue"))
    publication.doi = _optional_text(data.get("doi"))
    publication.url = _optional_text(data.get("url"))
    publication.pdf_url = _optional_text(data.get("pdf_url"))
    publication.source = _optional_text(data.get("source"))
    publication.source_id = _optional_text(data.get("source_id"))
    publication.is_preprint = _parse_bool(data.get("is_preprint"))
    publication.is_published = _parse_bool(data.get("is_published"), default=True)
    publication.is_visible = _parse_bool(data.get("is_visible"), default=True)
    _sync_authors(publication, authors_data)
    if tag_ids is not None:
        from services import tag_service

        tag_service.set_publication_tags(publication, tag_ids, commit=False)
    db.session.commit()
    return publication


def toggle_visibility(publication):
    """Toggle publication visibility."""
    publication.is_visible = not publication.is_visible
    db.session.commit()
    return publication


def import_publication(candidate, link_member_id=None, link_member_name=None):
    """
    Import a publication using deduplication rules.

    Returns a dict with keys: action, publication_id, title
    action is one of: created, updated, skipped
    """
    from services.deduplication_service import find_duplicate

    title = (candidate.get("title") or "").strip()
    if not title:
        return {"action": "skipped", "publication_id": None, "title": None}

    existing = find_duplicate(candidate)
    authors = list(candidate.get("authors") or [])

    if link_member_id and link_member_name:
        authors = _ensure_linked_member(authors, link_member_id, link_member_name)

    if existing:
        _merge_publication(existing, candidate)
        _merge_authors(existing, authors, link_member_id, link_member_name)
        db.session.commit()
        return {"action": "updated", "publication_id": existing.id, "title": existing.title}

    publication = Publication(
        title=title,
        abstract=candidate.get("abstract"),
        year=candidate.get("year"),
        publication_date=candidate.get("publication_date"),
        type=candidate.get("type"),
        venue=candidate.get("venue"),
        doi=candidate.get("doi"),
        url=candidate.get("url"),
        pdf_url=candidate.get("pdf_url"),
        source=candidate.get("source"),
        source_id=candidate.get("source_id"),
        is_preprint=bool(candidate.get("is_preprint")),
        is_published=bool(candidate.get("is_published", True)),
        is_visible=True,
    )
    db.session.add(publication)
    db.session.flush()
    _sync_authors(publication, authors)
    db.session.commit()
    return {"action": "created", "publication_id": publication.id, "title": publication.title}


def _merge_publication(publication, candidate):
    """Fill missing fields on an existing publication from sync metadata."""
    field_map = [
        "abstract",
        "year",
        "publication_date",
        "type",
        "venue",
        "doi",
        "url",
        "pdf_url",
        "source",
        "source_id",
    ]
    for field in field_map:
        new_value = candidate.get(field)
        if new_value and not getattr(publication, field):
            setattr(publication, field, new_value)

    if candidate.get("is_preprint") and not publication.is_preprint:
        publication.is_preprint = True
        publication.is_published = False


def _ensure_linked_member(authors, member_id, member_name):
    """
    Link the synced lab member onto a matching author row.

    Does not invent an extra author when the source already lists authors that
    do not match this member (avoids false attributions).
    """
    from services.author_matching import names_refer_to_same_person

    authors = list(authors)
    for author in authors:
        if author.get("member_id") == member_id:
            return authors

    for author in authors:
        author_name = (author.get("author_name") or "").strip()
        if not author_name:
            continue
        if author_name.lower() == member_name.strip().lower() or names_refer_to_same_person(
            author_name, member_name
        ):
            author["member_id"] = member_id
            return authors

    # ORCID summaries often omit co-author lists; attach the member alone then.
    if not any((author.get("author_name") or "").strip() for author in authors):
        authors.append(
            {
                "author_name": member_name,
                "member_id": member_id,
                "author_position": 1,
            }
        )
    return authors


def _merge_authors(publication, authors, link_member_id=None, link_member_name=None):
    """Merge source authors into a publication while preserving author order."""
    if link_member_id and link_member_name:
        authors = _ensure_linked_member(authors, link_member_id, link_member_name)

    incoming = _prepare_authors_data(authors)
    if incoming:
        _apply_author_order(publication, incoming, link_member_id, link_member_name)
        return

    if link_member_id and link_member_name:
        _ensure_existing_member_link(publication, link_member_id, link_member_name)


def _prepare_authors_data(authors):
    """Normalize author dicts and sort by declared position."""
    prepared = []
    for index, author in enumerate(authors or [], start=1):
        name = (author.get("author_name") or "").strip()
        if not name:
            continue
        prepared.append(
            {
                "author_name": name,
                "member_id": _parse_int(author.get("member_id")),
                "author_position": _parse_int(author.get("author_position")) or len(prepared) + 1,
            }
        )
    prepared.sort(key=lambda item: item["author_position"])
    return prepared


def _apply_author_order(publication, incoming, link_member_id=None, link_member_name=None):
    """Apply an ordered author list and renumber positions sequentially."""
    existing_map = {
        (author.author_name or "").strip().lower(): author for author in publication.authors
    }
    ordered = []
    used = set()

    for item in incoming:
        key = item["author_name"].lower()
        if key in used:
            continue
        used.add(key)

        if key in existing_map:
            author = existing_map[key]
            if item["member_id"]:
                author.member_id = item["member_id"]
        else:
            author = PublicationAuthor(
                publication_id=publication.id,
                author_name=item["author_name"],
                member_id=item["member_id"]
                or (
                    link_member_id
                    if key == (link_member_name or "").strip().lower()
                    else None
                ),
            )
            db.session.add(author)
            existing_map[key] = author
        ordered.append(author)

    for author in publication.ordered_authors():
        key = (author.author_name or "").strip().lower()
        if key not in used:
            ordered.append(author)
            used.add(key)

    for index, author in enumerate(ordered, start=1):
        author.author_position = index


def _ensure_existing_member_link(publication, link_member_id, link_member_name):
    """Link a lab member onto an existing matching author row if possible."""
    from services.author_matching import names_refer_to_same_person

    target = link_member_name.strip().lower()
    for author in publication.authors:
        author_name = (author.author_name or "").strip()
        if not author_name:
            continue
        if author_name.lower() == target or names_refer_to_same_person(
            author_name, link_member_name
        ):
            author.member_id = link_member_id
            return

    # Do not invent a new author row when co-authors are already present.
    if publication.authors:
        return

    db.session.add(
        PublicationAuthor(
            publication_id=publication.id,
            member_id=link_member_id,
            author_name=link_member_name,
            author_position=1,
        )
    )


def normalize_all_author_positions():
    """Renumber every publication's authors sequentially by current order."""
    publications = Publication.query.all()
    for publication in publications:
        for index, author in enumerate(publication.ordered_authors(), start=1):
            author.author_position = index
    db.session.commit()
    return len(publications)

