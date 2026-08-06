"""Identity checks beyond raw name matching (homonym protection)."""
import re

from services.author_matching import names_refer_to_same_person


_ARXIV_ID_RE = re.compile(
    r"(?:arxiv(?:\.org/(?:abs|pdf)/)?|doi\.org/10\.48550/arxiv\.|10\.48550/arxiv\.)"
    r"(\d{4}\.\d{4,5})(?:v\d+)?",
    flags=re.IGNORECASE,
)
_BARE_ARXIV_ID_RE = re.compile(r"^(\d{4}\.\d{4,5})(?:v\d+)?$", flags=re.IGNORECASE)


def normalize_arxiv_id(value):
    """Return a bare arXiv id (no version) or None."""
    if not value:
        return None
    text = str(value).strip()
    match = _BARE_ARXIV_ID_RE.match(text) or _ARXIV_ID_RE.search(text)
    if not match:
        return None
    return match.group(1).lower()


def author_names_from_candidate(candidate):
    """Extract author display names from a sync candidate."""
    names = []
    for author in candidate.get("authors") or []:
        name = (author.get("author_name") or "").strip()
        if name:
            names.append(name)
    return names


def candidate_lists_member(candidate, member_name):
    """True when the candidate author list includes the member by strict name match."""
    return any(
        names_refer_to_same_person(author_name, member_name)
        for author_name in author_names_from_candidate(candidate)
    )


def arxiv_candidate_is_trusted(
    candidate,
    member_name,
    *,
    known_coauthor_names=None,
    lab_member_names=None,
    known_arxiv_ids=None,
):
    """
    Decide whether an arXiv hit is safe to auto-link to a lab member.

    Name match alone is not enough (homonyms). Accept when at least one holds:
    - arXiv id already appears on the member's existing publications
    - a co-author overlaps the member's known co-author network
    - a co-author is another lab member
    """
    if not candidate_lists_member(candidate, member_name):
        return False

    arxiv_id = normalize_arxiv_id(candidate.get("source_id")) or normalize_arxiv_id(
        candidate.get("url")
    )
    known_ids = {normalize_arxiv_id(item) for item in (known_arxiv_ids or [])}
    known_ids.discard(None)
    if arxiv_id and arxiv_id in known_ids:
        return True

    other_authors = [
        name
        for name in author_names_from_candidate(candidate)
        if not names_refer_to_same_person(name, member_name)
    ]
    if not other_authors:
        # Solo-author arXiv hits are too ambiguous to auto-link.
        return False

    known_coauthors = [name for name in (known_coauthor_names or []) if name]
    lab_names = [name for name in (lab_member_names or []) if name]

    for author_name in other_authors:
        for known in known_coauthors:
            if names_refer_to_same_person(author_name, known):
                return True
        for lab_name in lab_names:
            if names_refer_to_same_person(lab_name, member_name):
                continue
            if names_refer_to_same_person(author_name, lab_name):
                return True

    return False


def collect_known_arxiv_ids_from_publications(publications):
    """Harvest arXiv ids already attached to a member's publications."""
    found = set()
    for publication in publications or []:
        for value in (
            getattr(publication, "source_id", None),
            getattr(publication, "doi", None),
            getattr(publication, "url", None),
            getattr(publication, "pdf_url", None),
        ):
            arxiv_id = normalize_arxiv_id(value)
            if arxiv_id:
                found.add(arxiv_id)
    return found


def collect_coauthor_names_for_member(member_id, publications_with_authors):
    """
    Build the set of co-author names seen on the member's existing publications.

    `publications_with_authors` should be an iterable of publications that already
    include an `.authors` collection (or ordered_authors()).
    """
    names = set()
    for publication in publications_with_authors or []:
        authors = getattr(publication, "authors", None) or []
        member_on_paper = False
        paper_names = []
        for author in authors:
            author_name = (getattr(author, "author_name", None) or "").strip()
            if not author_name:
                continue
            paper_names.append(author_name)
            if getattr(author, "member_id", None) == member_id:
                member_on_paper = True
        if not member_on_paper:
            continue
        for author_name in paper_names:
            names.add(author_name)
    return names
