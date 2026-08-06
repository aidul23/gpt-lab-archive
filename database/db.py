"""Database setup and SQLAlchemy models."""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class Member(db.Model):
    """Lab member profile."""

    __tablename__ = "members"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(255))
    email = db.Column(db.String(255))
    orcid = db.Column(db.String(64))
    openalex_author_id = db.Column(db.String(64))
    profile_url = db.Column(db.String(512))
    photo_url = db.Column(db.String(512))
    photo_filename = db.Column(db.String(255))
    bio = db.Column(db.Text)
    approval_status = db.Column(db.String(32), default="approved", nullable=False)
    is_self_registered = db.Column(db.Boolean, default=False, nullable=False)
    submitted_at = db.Column(db.DateTime)
    reviewed_at = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    authorships = db.relationship(
        "PublicationAuthor",
        back_populates="member",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<Member {self.name}>"

    def photo_display_url(self):
        """Return the member photo URL or a generated placeholder avatar."""
        if self.photo_filename:
            return f"/static/uploads/members/{self.photo_filename}"
        if self.photo_url:
            return self.photo_url
        from urllib.parse import quote

        name = quote(self.name)
        return (
            "https://ui-avatars.com/api/"
            f"?name={name}&size=256&background=4e008e&color=ffffff&bold=true"
        )

    def is_publicly_visible(self):
        """Return True when the profile should appear on public pages."""
        return self.approval_status == "approved" and self.active

    def approval_label(self):
        """Human-readable approval status."""
        return self.approval_status.replace("_", " ").title()

    def initials(self):
        """Return initials for avatar fallback text."""
        parts = [part for part in self.name.split() if part]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class Publication(db.Model):
    """Publication or preprint record."""

    __tablename__ = "publications"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    abstract = db.Column(db.Text)
    year = db.Column(db.Integer)
    publication_date = db.Column(db.String(32))
    type = db.Column(db.String(64))
    venue = db.Column(db.String(512))
    doi = db.Column(db.String(255))
    arxiv_id = db.Column(db.String(64))
    url = db.Column(db.String(512))
    pdf_url = db.Column(db.String(512))
    source = db.Column(db.String(64))
    source_id = db.Column(db.String(255))
    is_preprint = db.Column(db.Boolean, default=False, nullable=False)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    is_visible = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    authors = db.relationship(
        "PublicationAuthor",
        back_populates="publication",
        cascade="all, delete-orphan",
        order_by="PublicationAuthor.author_position, PublicationAuthor.id",
    )
    tags = db.relationship(
        "Tag",
        secondary="publication_tags",
        back_populates="publications",
        lazy="joined",
    )

    def ordered_authors(self):
        """Return authors sorted by position, then id."""
        return sorted(
            self.authors,
            key=lambda author: (
                author.author_position is None,
                author.author_position if author.author_position is not None else 10**9,
                author.id or 0,
            ),
        )

    def author_display(self):
        """Comma-separated author names for display."""
        authors = self.ordered_authors()
        if not authors:
            return "Unknown authors"
        return ", ".join(author.author_name for author in authors)

    def tags_by_kind(self, kind):
        """Return tags or themes attached to this publication."""
        return [tag for tag in self.tags if tag.kind == kind]

    def __repr__(self):
        return f"<Publication {self.title[:40]}>"


class PublicationAuthor(db.Model):
    """Link between publications and lab members (or external author names)."""

    __tablename__ = "publication_authors"

    id = db.Column(db.Integer, primary_key=True)
    publication_id = db.Column(
        db.Integer,
        db.ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=False,
    )
    member_id = db.Column(
        db.Integer,
        db.ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_name = db.Column(db.String(255), nullable=False)
    author_position = db.Column(db.Integer)

    publication = db.relationship("Publication", back_populates="authors")
    member = db.relationship("Member", back_populates="authorships")

    def __repr__(self):
        return f"<PublicationAuthor {self.author_name}>"


class SyncLog(db.Model):
    """Log entry for future external sync operations."""

    __tablename__ = "sync_logs"

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(64))
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    status = db.Column(db.String(64))
    message = db.Column(db.Text)

    def __repr__(self):
        return f"<SyncLog {self.source} {self.status}>"


class Tag(db.Model):
    """Publication tag or research theme."""

    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    slug = db.Column(db.String(128), nullable=False, unique=True)
    kind = db.Column(db.String(32), nullable=False, default="tag")
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)

    publications = db.relationship(
        "Publication",
        secondary="publication_tags",
        back_populates="tags",
    )

    def __repr__(self):
        return f"<Tag {self.name}>"


class PublicationTag(db.Model):
    """Association between publications and tags/themes."""

    __tablename__ = "publication_tags"

    publication_id = db.Column(
        db.Integer,
        db.ForeignKey("publications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id = db.Column(
        db.Integer,
        db.ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )


class PublicationRequest(db.Model):
    """Member-submitted request to add a missing publication."""

    __tablename__ = "publication_requests"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer,
        db.ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
    )
    requester_email = db.Column(db.String(255))
    title = db.Column(db.Text, nullable=False)
    year = db.Column(db.Integer)
    doi = db.Column(db.String(255))
    url = db.Column(db.String(512))
    venue = db.Column(db.String(512))
    authors_text = db.Column(db.Text)
    notes = db.Column(db.Text)
    status = db.Column(db.String(32), default="pending", nullable=False)
    submitted_at = db.Column(db.DateTime, default=utcnow)
    reviewed_at = db.Column(db.DateTime)
    created_publication_id = db.Column(
        db.Integer,
        db.ForeignKey("publications.id", ondelete="SET NULL"),
        nullable=True,
    )

    member = db.relationship("Member", backref=db.backref("publication_requests", lazy="dynamic"))
    created_publication = db.relationship("Publication")

    def status_label(self):
        """Human-readable request status."""
        return (self.status or "pending").replace("_", " ").title()

    def __repr__(self):
        return f"<PublicationRequest {self.id} {self.status}>"


class PublicationOverride(db.Model):
    """Per-member allowlist / blocklist keyed by DOI or arXiv ID."""

    __tablename__ = "publication_overrides"
    __table_args__ = (
        db.UniqueConstraint(
            "member_id",
            "key_type",
            "key_value",
            name="uq_publication_override_member_key",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer,
        db.ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
    )
    key_type = db.Column(db.String(16), nullable=False)  # doi | arxiv
    key_value = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(16), nullable=False)  # allow | block
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    member = db.relationship("Member", backref=db.backref("publication_overrides", lazy="dynamic"))

    def __repr__(self):
        return f"<PublicationOverride {self.action} {self.key_type}:{self.key_value}>"


class PublicationMatchCandidate(db.Model):
    """Tier 3 scored candidates awaiting manual confirmation."""

    __tablename__ = "publication_match_candidates"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer,
        db.ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.Text, nullable=False)
    year = db.Column(db.Integer)
    doi = db.Column(db.String(255))
    arxiv_id = db.Column(db.String(64))
    venue = db.Column(db.String(512))
    authors_json = db.Column(db.Text)
    score = db.Column(db.Float)
    score_breakdown_json = db.Column(db.Text)
    payload_json = db.Column(db.Text)
    status = db.Column(db.String(32), default="pending", nullable=False)
    match_reason = db.Column(db.String(255))
    created_publication_id = db.Column(
        db.Integer,
        db.ForeignKey("publications.id", ondelete="SET NULL"),
        nullable=True,
    )
    submitted_at = db.Column(db.DateTime, default=utcnow)
    reviewed_at = db.Column(db.DateTime)

    member = db.relationship(
        "Member", backref=db.backref("match_candidates", lazy="dynamic")
    )
    created_publication = db.relationship("Publication")

    def status_label(self):
        return (self.status or "pending").replace("_", " ").title()

    def __repr__(self):
        return f"<PublicationMatchCandidate {self.id} {self.status}>"


def init_db(app):
    """Initialize database with the Flask app."""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _ensure_member_bio_column()
        _ensure_publication_arxiv_column()
        _normalize_existing_author_positions()


def _normalize_existing_author_positions():
    """Fix author order for publications already stored in the database."""
    from services.publication_service import normalize_all_author_positions

    normalize_all_author_positions()


def _ensure_member_bio_column():
    """Add newer member columns to existing SQLite databases."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if "members" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("members")}
    migrations = [
        ("bio", "ALTER TABLE members ADD COLUMN bio TEXT"),
        ("photo_filename", "ALTER TABLE members ADD COLUMN photo_filename TEXT"),
        ("approval_status", "ALTER TABLE members ADD COLUMN approval_status TEXT DEFAULT 'approved'"),
        ("is_self_registered", "ALTER TABLE members ADD COLUMN is_self_registered BOOLEAN DEFAULT 0"),
        ("submitted_at", "ALTER TABLE members ADD COLUMN submitted_at DATETIME"),
        ("reviewed_at", "ALTER TABLE members ADD COLUMN reviewed_at DATETIME"),
    ]
    for column_name, statement in migrations:
        if column_name not in columns:
            db.session.execute(text(statement))
    db.session.commit()


def _ensure_publication_arxiv_column():
    """Add arxiv_id to publications on existing databases."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if "publications" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("publications")}
    if "arxiv_id" not in columns:
        db.session.execute(text("ALTER TABLE publications ADD COLUMN arxiv_id TEXT"))
        db.session.commit()
