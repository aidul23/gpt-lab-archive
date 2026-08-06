# GPT Lab Publications & Research Archive

A Flask web application for the **[GPT Lab](https://gpt-lab.eu/)** research group at **Tampere University**. This is a dedicated **publications showcase** — a place to browse lab members, their research tracks, papers, preprints, and research themes in one place. It complements the main lab website at [gpt-lab.eu](https://gpt-lab.eu/).

## Features

- **Home page** with summary counts and recent publications
- **Members** listing and member detail pages with publications grouped by year
- **Self-registration** at `/join` — lab members submit their own profile for admin review
- **Admin approval workflow** — pending profiles are hidden until verified and approved
- **Profile photo uploads** — images stored under `static/uploads/members/` and served locally
- **Publications** page with filtering and text search
- **Preprints** page for unpublished works
- **Publication detail** pages with full metadata
- **Admin pages** for managing members and publications (no login in v1)
- **Deduplication helper** for future sync workflows
- **Sync stub service** with placeholder API functions

## Tech Stack

- **Backend:** Flask
- **Database:** SQLite via Flask-SQLAlchemy
- **Frontend:** Jinja2 templates + custom CSS

## Project Structure

```
lab-publications-portal/
  app.py                          # Flask routes and application entry point
  config.py                       # Configuration settings
  requirements.txt                # Python dependencies
  README.md
  database/
    schema.sql                    # Raw SQL schema reference
    seed.py                       # Seed script with sample data
    db.py                         # SQLAlchemy models and DB setup
  services/
    publication_service.py        # Publication queries and CRUD
    member_service.py             # Member queries and CRUD
    deduplication_service.py      # Duplicate detection helpers
    sync_stub_service.py          # Placeholder sync functions
  templates/                      # Jinja2 HTML templates
  static/css/style.css            # Site styling
```

## Setup Instructions

### 1. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create and seed the database

The seed script creates the SQLite database and loads sample data:

```bash
python database/seed.py
```

This creates `database/lab_publications.db` with:
- 4 sample lab members
- 8 sample publications (published papers, preprints, and one hidden draft)

You can also inspect the schema in `database/schema.sql`. Tables are created automatically by SQLAlchemy when seeding or running the app.

### 4. Run the Flask app

```bash
python app.py
```

Open [http://127.0.0.1:5001](http://127.0.0.1:5001) in your browser.

The app defaults to port **5001** because macOS often uses port 5000 for AirPlay Receiver. To use a different port:

```bash
FLASK_PORT=8080 python app.py
```

### 5. Log in to admin

Admin routes are password protected. Default development password:

```text
admin
```

Override it with an environment variable before starting the app:

```bash
export ADMIN_PASSWORD="your-secure-password"
python app.py
```

For production, you can instead set a pre-hashed password:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-secure-password'))"
export ADMIN_PASSWORD_HASH="paste-hash-here"
python app.py
```

Admin login URL: [http://127.0.0.1:5001/admin/login](http://127.0.0.1:5001/admin/login)

## Main Routes

| Route | Description |
|-------|-------------|
| `/` | Home page with counts and recent publications |
| `/members` | Approved lab members |
| `/join` | Submit a new member profile for admin review |
| `/members/<id>` | Member profile and publications (approved only) |
| `/publications` | Browse and filter publications |
| `/preprints` | Preprints only |
| `/publications/<id>` | Publication detail page |
| `/admin/login` | Admin login |
| `/admin/logout` | Admin logout |
| `/admin` | Admin dashboard |
| `/admin/members` | Manage members |
| `/admin/publications` | Manage publications |
| `/admin/sync` | Import from external APIs |
| `/publications/export.csv` | Download filtered publications as CSV |
| `/publications/export.bib` | Download filtered publications as BibTeX |
| `/members/<id>/export.csv` | Download a member's publications as CSV |
| `/members/<id>/export.bib` | Download a member's publications as BibTeX |
| `/themes` | Browse research themes |
| `/themes/<slug>` | Publications for a research theme |
| `/admin/tags` | Manage tags and themes |

## Exporting Publications

Public export links are available on the Publications, Preprints, and Member detail pages. Exports on the Publications page respect the current filters (year, type, member, search, etc.).

Admin exports on **Manage Publications** include hidden records and an extra `is_visible` column in CSV output.

Supported formats:

- **CSV** — spreadsheet-friendly metadata
- **BibTeX** — citation manager import

## Syncing Publications

### Automatic sync for all members

The app can sync **every registered lab member** from:

| Source | What it imports |
|--------|-----------------|
| **ORCID** | Public works on the member's ORCID profile |
| **OpenAlex** | Recent works for the member's OpenAlex author ID |
| **arXiv** | Preprints matching the member's author name |
| **Crossref** | Enriched metadata for publications that already have DOIs |

**Manual sync all (admin UI):** go to `/admin/sync` and click **Sync All Active Members Now**.

**Command-line / cron:**

```bash
python scripts/sync_all.py
```

Example cron entry (daily at 2 AM):

```bash
0 2 * * * cd /path/to/gpt-lab-archive && ./venv/bin/python scripts/sync_all.py
```

**Background sync while the app is running:**

```bash
export AUTO_SYNC_ENABLED=1
export AUTO_SYNC_INTERVAL_HOURS=24
export AUTO_SYNC_ON_STARTUP=1   # optional: run once when app starts
python app.py
```

Members need **real ORCID and/or OpenAlex IDs** on their profiles for those sources to return data. arXiv preprints are matched to a specific member by **first and last name** on the author list.

### Auto-load when creating a member profile

When you **create or save** a member in admin, the app automatically runs a per-member sync:

1. **ORCID** → published papers and ORCID-listed preprints
2. **OpenAlex** → published papers and OpenAlex preprints
3. **arXiv** → preprints where this member appears as an author
4. **Crossref** → enriches metadata for existing DOIs

After saving, open the member's public profile to see **Published Papers** and **Preprints** in separate sections.

### Manual sync (single source)

Admin users can also import publications one source at a time at `/admin/sync`:

| Source | Requires | Notes |
|--------|----------|-------|
| ORCID | Member ORCID | Imports public works from an ORCID profile |
| OpenAlex | Member OpenAlex author ID | Imports recent works for an author |
| Crossref | DOI | Imports a single publication by DOI |
| arXiv | Search query or arXiv ID | Imports matching preprints |

Imported records are deduplicated automatically using DOI, source ID, or normalized title. Sync activity is stored in the `sync_logs` table.

Optional environment variable for API etiquette:

```bash
export CONTACT_EMAIL="your-lab@example.edu"
```

## Database Tables

### `members`
Lab member profiles with ORCID and OpenAlex IDs for future syncing.

| Column | Description |
|--------|-------------|
| `name` | Full name (required) |
| `role` | e.g. PI, PhD Student |
| `email` | Contact email |
| `orcid` | ORCID identifier |
| `openalex_author_id` | OpenAlex author ID |
| `profile_url` | External profile link |
| `photo_filename` | Uploaded profile photo stored under `static/uploads/members/` |
| `photo_url` | Legacy external photo URL (optional fallback) |
| `bio` | Short profile biography |
| `approval_status` | `pending`, `approved`, or `rejected` |
| `is_self_registered` | Whether the profile was submitted via `/join` |
| `submitted_at` | When a self-registered profile was submitted |
| `reviewed_at` | When an admin approved or rejected the profile |
| `active` | Whether the member is currently active |

Only **approved** and **active** profiles appear on public member pages.

### Member registration and approval

1. A lab member opens **Join Lab** (`/join`) and fills in their profile, including an optional photo upload.
2. The profile is saved with `approval_status = pending` and is **not** shown publicly.
3. An admin reviews the submission under **Admin → Manage Members**, verifies ORCID/OpenAlex IDs and other details, then clicks **Approve** or **Reject**.
4. On approval, the app automatically syncs publications from ORCID, OpenAlex, arXiv, and Crossref.

Uploaded photos are saved to `static/uploads/members/` and displayed from `/static/uploads/members/<filename>`.

### `publications`
Publication and preprint records.

| Column | Description |
|--------|-------------|
| `title` | Publication title (required) |
| `abstract` | Abstract text |
| `year` | Publication year |
| `publication_date` | Date string (e.g. YYYY-MM-DD) |
| `type` | article, conference, dataset, etc. |
| `venue` | Journal, conference, or repository |
| `doi` | Digital Object Identifier |
| `url` | Landing page URL |
| `pdf_url` | Direct PDF link |
| `source` | Where data came from (manual, crossref, etc.) |
| `source_id` | External source identifier |
| `is_preprint` | Whether this is a preprint |
| `is_published` | Whether formally published |
| `is_visible` | Whether shown on public pages |

### `publication_authors`
Links publications to authors. Supports both lab members (`member_id`) and external author names.

### `tags`
Labels and research themes that can be attached to publications.

| Column | Description |
|--------|-------------|
| `name` | Display name (unique) |
| `slug` | URL-friendly identifier |
| `kind` | `tag` or `theme` |
| `description` | Optional summary text |

### `publication_tags`
Many-to-many link between publications and tags/themes.

### `sync_logs`
Stores history for automated sync operations, including source, timestamps, status, and message.

## Deduplication Rules

The deduplication service (`services/deduplication_service.py`) identifies duplicate publications using:

1. Matching DOI
2. Matching `source` + `source_id`
3. Matching normalized title (lowercase, no punctuation, collapsed whitespace)

## Completed Improvements

- Admin authentication with session login (`/admin/login`)
- Real syncing from ORCID, OpenAlex, Crossref, and arXiv (`/admin/sync`)
- Sync logging in `sync_logs`
- Deduplication during automated imports
- CSV and BibTeX export for publications
- Publication tags and research themes
- Member photos and richer profile pages
- Automatic sync for all registered members (ORCID, OpenAlex, arXiv, Crossref enrichment)

## Future Improvements

- Deploy with Gunicorn behind nginx
- Add pagination for large publication lists
- Support ORCID OAuth for member self-updates

## Development Notes

- Admin pages require login. Set `ADMIN_PASSWORD` or `ADMIN_PASSWORD_HASH` before deploying publicly.
- Hidden publications (`is_visible = false`) are excluded from public pages but visible in admin.
- External sync requires network access and uses public APIs only.
