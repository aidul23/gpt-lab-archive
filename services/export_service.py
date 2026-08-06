"""Export publications to CSV and BibTeX."""
import csv
import io
import re
import unicodedata


CSV_FIELDS = [
    "id",
    "title",
    "authors",
    "year",
    "publication_date",
    "type",
    "venue",
    "doi",
    "url",
    "pdf_url",
    "abstract",
    "source",
    "source_id",
    "is_preprint",
    "is_published",
    "tags",
    "themes",
    "is_visible",
]


def publications_to_csv(publications, include_admin_fields=False):
    """Convert publications to CSV text."""
    output = io.StringIO()
    fields = CSV_FIELDS if include_admin_fields else [f for f in CSV_FIELDS if f != "is_visible"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()

    for publication in publications:
        row = {
            "id": publication.id,
            "title": publication.title or "",
            "authors": publication.author_display(),
            "year": publication.year or "",
            "publication_date": publication.publication_date or "",
            "type": publication.type or "",
            "venue": publication.venue or "",
            "doi": publication.doi or "",
            "url": publication.url or "",
            "pdf_url": publication.pdf_url or "",
            "abstract": publication.abstract or "",
            "source": publication.source or "",
            "source_id": publication.source_id or "",
            "is_preprint": publication.is_preprint,
            "is_published": publication.is_published,
            "tags": ", ".join(tag.name for tag in publication.tags_by_kind("tag")),
            "themes": ", ".join(theme.name for theme in publication.tags_by_kind("theme")),
            "is_visible": publication.is_visible,
        }
        writer.writerow(row)

    return output.getvalue()


def publications_to_bibtex(publications):
    """Convert publications to a BibTeX string."""
    entries = []
    used_keys = set()

    for publication in publications:
        entry_type = _bibtex_entry_type(publication.type, publication.is_preprint)
        cite_key = _make_cite_key(publication, used_keys)
        lines = [f"@{entry_type}{{{cite_key},"]
        lines.append(f"  title = {{{_bibtex_escape(publication.title)}}},")
        lines.append(f"  author = {{{_format_bibtex_authors(publication)}}},")

        if publication.year:
            lines.append(f"  year = {{{publication.year}}},")
        if publication.publication_date:
            lines.append(f"  date = {{{_bibtex_escape(publication.publication_date)}}},")
        if publication.doi:
            lines.append(f"  doi = {{{_bibtex_escape(publication.doi)}}},")
        if publication.url:
            lines.append(f"  url = {{{_bibtex_escape(publication.url)}}},")
        if publication.pdf_url:
            lines.append(f"  pdf = {{{_bibtex_escape(publication.pdf_url)}}},")
        if publication.abstract:
            lines.append(f"  abstract = {{{_bibtex_escape(publication.abstract)}}},")

        if entry_type == "inproceedings" and publication.venue:
            lines.append(f"  booktitle = {{{_bibtex_escape(publication.venue)}}},")
        elif publication.venue:
            lines.append(f"  journal = {{{_bibtex_escape(publication.venue)}}},")

        if publication.source_id:
            lines.append(f"  note = {{{_bibtex_escape(publication.source + ': ' + publication.source_id if publication.source else publication.source_id)}}},")

        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("}")
        entries.append("\n".join(lines))

    return "\n\n".join(entries) + ("\n" if entries else "")


def _bibtex_entry_type(pub_type, is_preprint):
    """Map local publication types to BibTeX entry types."""
    if is_preprint:
        return "unpublished"
    if pub_type == "conference":
        return "inproceedings"
    if pub_type == "article":
        return "article"
    return "misc"


def _format_bibtex_authors(publication):
    """Format authors for BibTeX."""
    authors = publication.ordered_authors()
    if not authors:
        return "Unknown"
    return " and ".join(_bibtex_escape(author.author_name) for author in authors)


def _make_cite_key(publication, used_keys):
    """Generate a stable, unique BibTeX citation key."""
    first_author = "unknown"
    ordered = publication.ordered_authors()
    if ordered:
        first_author = ordered[0].author_name.split()[-1]

    first_author = _slugify(first_author) or "unknown"
    year = publication.year or "nodate"
    title_word = _slugify((publication.title or "untitled").split()[0]) or "untitled"
    base_key = f"{first_author}{year}{title_word}"

    key = base_key
    suffix = 97
    while key in used_keys:
        key = f"{base_key}{chr(suffix)}"
        suffix += 1
    used_keys.add(key)
    return key


def _slugify(value):
    """Create a BibTeX-safe slug."""
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]", "", value)
    return value.lower()


def _bibtex_escape(value):
    """Escape text for BibTeX field values."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{").replace("}", "\\}")
    return text
