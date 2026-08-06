"""Strict person-name matching for author ↔ member linking."""
import re


# Leading honorific-style tokens often placed before a real given name.
# Only stripped when another given name follows (e.g. "Md Aidul" → "Aidul").
# Sole first names like "Muhammad" are kept.
_LEADING_NAME_PREFIXES = {
    "md",
    "mohd",
    "abd",
    "abdul",
    "al",
}

_TITLE_PREFIXES = {"dr", "prof", "professor"}


def names_refer_to_same_person(author_name, member_name):
    """
    Return True only when the author string is the same person as the member.

    Rejects longer names that merely share a first+last prefix, e.g.
    member "Muhammad Waseem" must not match "Muhammad Danish Waseem".
    """
    author_tokens = name_tokens(author_name)
    member_tokens = name_tokens(member_name)
    if not author_tokens or not member_tokens:
        return False

    if author_tokens[-1] != member_tokens[-1]:
        return False

    author_given_raw = author_tokens[:-1]
    member_given_raw = member_tokens[:-1]
    author_given = strip_leading_prefixes(author_given_raw)
    member_given = strip_leading_prefixes(member_given_raw)

    # Last-name-only member profile: only accept last-name-only author strings.
    if not member_given_raw:
        return not author_given_raw

    # Exact given-name sequence (after stripping leading Md-style prefixes).
    if author_given == member_given and member_given:
        return True

    # Same token count with full names or compatible initials:
    # "M. A. Islam" ↔ "Md Aidul Islam", "M. Waseem" ↔ "Muhammad Waseem".
    if len(author_given_raw) == len(member_given_raw) and all(
        _token_matches(author_token, member_token)
        for author_token, member_token in zip(author_given_raw, member_given_raw)
    ):
        return True

    # Author omitted leading prefixes only: "Aidul Islam" ↔ "Md Aidul Islam".
    if author_given and author_given == member_given:
        return True
    if (
        author_given
        and len(author_given) == len(member_given)
        and all(
            _token_matches(author_token, member_token)
            for author_token, member_token in zip(author_given, member_given)
        )
    ):
        return True

    # Single given-name / single initial against the core given name only.
    # Intentionally rejects extra middle names on the author side.
    if (
        len(member_given) == 1
        and len(author_given) == 1
        and _token_matches(author_given[0], member_given[0])
    ):
        return True

    return False

def preferred_given_name(name):
    """Prefer a searchable given name, skipping leading Md-style prefixes."""
    tokens = name_tokens(name)
    if len(tokens) < 2:
        return None
    given = strip_leading_prefixes(tokens[:-1])
    return given[0] if given else None


def last_name(name):
    """Extract the last-name token from a display name."""
    tokens = name_tokens(name)
    return tokens[-1] if tokens else ""


def given_name_tokens(name):
    """Return given-name tokens (before the last name)."""
    tokens = name_tokens(name)
    return tokens[:-1] if len(tokens) > 1 else []


def strip_leading_prefixes(tokens):
    """Remove leading Md/Mohd-style prefixes when a real given name follows."""
    result = list(tokens or [])
    while len(result) > 1 and result[0] in _LEADING_NAME_PREFIXES:
        result.pop(0)
    return result


def name_tokens(name):
    """Normalize a person name into lowercase alphanumeric tokens."""
    cleaned = re.sub(
        r"^(dr|prof|professor)\.?\s+",
        "",
        (name or "").strip(),
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.lower().replace(",", " ").replace(".", " ")
    return [
        part
        for part in cleaned.split()
        if part and part not in _TITLE_PREFIXES
    ]


def _token_matches(author_token, member_token):
    """Match a full token or a compatible initial."""
    if author_token == member_token:
        return True
    if len(author_token) == 1 and member_token.startswith(author_token):
        return True
    if len(member_token) == 1 and author_token.startswith(member_token):
        return True
    return False
