"""Tag and research theme operations."""
import re

from database.db import Publication, PublicationTag, Tag, db
from services.lab_themes import GPT_LAB_THEMES


def get_all_tags(kind=None):
    """Return all tags, optionally filtered by kind."""
    query = Tag.query
    if kind:
        query = query.filter_by(kind=kind)
    return query.order_by(Tag.name).all()


def ensure_gpt_lab_themes(*, replace_demo_themes=True):
    """
    Upsert the eight GPT Lab research pillars as themes.

    When replace_demo_themes is True, remove leftover demo theme names that
    are not part of the official pillar list (e.g. seed Machine Learning).
    """
    pillar_slugs = {item["slug"] for item in GPT_LAB_THEMES}
    pillar_names = {item["name"] for item in GPT_LAB_THEMES}
    created = 0
    updated = 0

    for item in GPT_LAB_THEMES:
        existing = Tag.query.filter(
            (Tag.slug == item["slug"]) | (Tag.name == item["name"])
        ).first()
        if existing:
            existing.name = item["name"]
            existing.slug = item["slug"]
            existing.kind = "theme"
            existing.description = item["description"]
            updated += 1
        else:
            db.session.add(
                Tag(
                    name=item["name"],
                    slug=item["slug"],
                    kind="theme",
                    description=item["description"],
                )
            )
            created += 1

    removed = 0
    if replace_demo_themes:
        demo_names = {
            "Machine Learning",
            "Computational Chemistry",
            "Experimental Design",
        }
        for theme in Tag.query.filter_by(kind="theme").all():
            if theme.slug in pillar_slugs or theme.name in pillar_names:
                continue
            if theme.name in demo_names or theme.slug in {
                "machine-learning",
                "computational-chemistry",
                "experimental-design",
            }:
                PublicationTag.query.filter_by(tag_id=theme.id).delete()
                db.session.delete(theme)
                removed += 1

    db.session.commit()
    return {"created": created, "updated": updated, "removed": removed}


def get_tag_by_id(tag_id):
    """Return a tag by ID."""
    return Tag.query.get(tag_id)


def get_tag_by_slug(slug):
    """Return a tag by slug."""
    return Tag.query.filter_by(slug=slug).first()


def get_themes_with_counts():
    """Return research themes with publication counts."""
    themes = get_all_tags(kind="theme")
    results = []
    for theme in themes:
        count = (
            db.session.query(PublicationTag.publication_id)
            .join(Publication)
            .filter(
                PublicationTag.tag_id == theme.id,
                Publication.is_visible.is_(True),
            )
            .distinct()
            .count()
        )
        results.append({"theme": theme, "count": count})
    return results


def create_tag(data):
    """Create a tag or research theme."""
    name = (data.get("name") or "").strip()
    kind = (data.get("kind") or "tag").strip().lower()
    if kind not in {"tag", "theme"}:
        kind = "tag"

    tag = Tag(
        name=name,
        slug=_make_slug(name, kind),
        kind=kind,
        description=_optional_text(data.get("description")),
    )
    db.session.add(tag)
    db.session.commit()
    return tag


def update_tag(tag, data):
    """Update a tag or research theme."""
    name = (data.get("name") or tag.name).strip()
    tag.name = name
    tag.slug = _make_slug(name, tag.kind, exclude_id=tag.id)
    tag.description = _optional_text(data.get("description"))
    db.session.commit()
    return tag


def delete_tag(tag_id):
    """Delete a tag and remove all publication links."""
    tag = Tag.query.get(tag_id)
    if not tag:
        return None
    name = tag.name
    db.session.delete(tag)
    db.session.commit()
    return {"name": name}


def set_publication_tags(publication, tag_ids, commit=True):
    """Replace tags linked to a publication."""
    tag_ids = {int(tag_id) for tag_id in tag_ids if str(tag_id).strip().isdigit()}
    publication.tags = Tag.query.filter(Tag.id.in_(tag_ids)).all() if tag_ids else []
    if commit:
        db.session.commit()
    return publication


def parse_tag_ids_from_form(form):
    """Parse selected tag IDs from a form submission."""
    if hasattr(form, "getlist"):
        return form.getlist("tag_ids")
    return form.get("tag_ids") or []


def _make_slug(name, kind, exclude_id=None):
    """Generate a unique slug from a display name."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or kind
    slug = base
    suffix = 2
    while True:
        query = Tag.query.filter_by(slug=slug)
        if exclude_id:
            query = query.filter(Tag.id != exclude_id)
        if not query.first():
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


def _optional_text(value):
    """Normalize optional text fields."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None
