"""Persistent per-member allowlist / blocklist for publication matching."""
from services.api_client_utils import normalize_doi
from services.identity_verification import normalize_arxiv_id

from database.db import PublicationOverride, db, utcnow


ACTION_ALLOW = "allow"
ACTION_BLOCK = "block"
KEY_DOI = "doi"
KEY_ARXIV = "arxiv"


def normalize_override_key(key_type, key_value):
    """Normalize an override key; return (type, value) or (None, None)."""
    key_type = (key_type or "").strip().lower()
    if key_type == KEY_DOI:
        value = normalize_doi(key_value)
        return (KEY_DOI, value.lower()) if value else (None, None)
    if key_type in {KEY_ARXIV, "arxiv_id"}:
        value = normalize_arxiv_id(key_value)
        return (KEY_ARXIV, value) if value else (None, None)
    return None, None


def keys_for_record(record):
    """Return override keys present on a unified record or candidate."""
    keys = []
    doi = normalize_doi(record.get("doi"))
    if doi:
        keys.append((KEY_DOI, doi.lower()))
    arxiv_id = normalize_arxiv_id(record.get("arxiv_id"))
    if arxiv_id:
        keys.append((KEY_ARXIV, arxiv_id))
    return keys


def get_overrides_for_member(member_id):
    """Return all overrides for a member."""
    return PublicationOverride.query.filter_by(member_id=member_id).all()


def override_maps(member_id):
    """Return ({key: action}, ...) for fast lookup."""
    mapping = {}
    for row in get_overrides_for_member(member_id):
        mapping[(row.key_type, row.key_value.lower())] = row.action
    return mapping


def is_blocked(record, member_id, mapping=None):
    """Blocklist always wins over automated inclusion."""
    mapping = mapping if mapping is not None else override_maps(member_id)
    for key in keys_for_record(record):
        if mapping.get(key) == ACTION_BLOCK:
            return True
    return False


def is_allowed(record, member_id, mapping=None):
    """Return True when an allowlist entry matches the record."""
    mapping = mapping if mapping is not None else override_maps(member_id)
    for key in keys_for_record(record):
        if mapping.get(key) == ACTION_ALLOW:
            return True
    return False


def upsert_override(member_id, key_type, key_value, action, note=None):
    """Create or update an override. Block/allow replace each other."""
    key_type, key_value = normalize_override_key(key_type, key_value)
    if not key_type or not key_value:
        raise ValueError("Override requires a valid DOI or arXiv ID.")
    action = (action or "").strip().lower()
    if action not in {ACTION_ALLOW, ACTION_BLOCK}:
        raise ValueError("Override action must be allow or block.")

    row = PublicationOverride.query.filter_by(
        member_id=member_id,
        key_type=key_type,
        key_value=key_value,
    ).first()
    if row:
        row.action = action
        row.note = note
        row.updated_at = utcnow()
    else:
        row = PublicationOverride(
            member_id=member_id,
            key_type=key_type,
            key_value=key_value,
            action=action,
            note=note,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.session.add(row)
    db.session.commit()
    return row


def block_record_for_member(member_id, record, note=None):
    """Add blocklist entries for every durable ID on the record."""
    created = []
    for key_type, key_value in keys_for_record(record):
        created.append(
            upsert_override(member_id, key_type, key_value, ACTION_BLOCK, note=note)
        )
    return created


def allow_record_for_member(member_id, record, note=None):
    """Add allowlist entries for every durable ID on the record."""
    created = []
    for key_type, key_value in keys_for_record(record):
        created.append(
            upsert_override(member_id, key_type, key_value, ACTION_ALLOW, note=note)
        )
    return created
