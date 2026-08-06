-- Lab Publications Portal database schema

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT,
    email TEXT,
    orcid TEXT,
    openalex_author_id TEXT,
    profile_url TEXT,
    photo_url TEXT,
    photo_filename TEXT,
    bio TEXT,
    approval_status TEXT NOT NULL DEFAULT 'approved',
    is_self_registered BOOLEAN DEFAULT 0,
    submitted_at DATETIME,
    reviewed_at DATETIME,
    active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    abstract TEXT,
    year INTEGER,
    publication_date TEXT,
    type TEXT,
    venue TEXT,
    doi TEXT,
    arxiv_id TEXT,
    url TEXT,
    pdf_url TEXT,
    source TEXT,
    source_id TEXT,
    is_preprint BOOLEAN DEFAULT 0,
    is_published BOOLEAN DEFAULT 1,
    is_visible BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS publication_authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id INTEGER NOT NULL,
    member_id INTEGER,
    author_name TEXT NOT NULL,
    author_position INTEGER,
    FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE,
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sync_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    status TEXT,
    message TEXT
);

CREATE INDEX IF NOT EXISTS idx_publications_year ON publications(year);
CREATE INDEX IF NOT EXISTS idx_publications_doi ON publications(doi);
CREATE INDEX IF NOT EXISTS idx_publications_visible ON publications(is_visible);
CREATE INDEX IF NOT EXISTS idx_publication_authors_member ON publication_authors(member_id);
CREATE INDEX IF NOT EXISTS idx_publication_authors_publication ON publication_authors(publication_id);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'tag',
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS publication_tags (
    publication_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (publication_id, tag_id),
    FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tags_kind ON tags(kind);
CREATE INDEX IF NOT EXISTS idx_publication_tags_tag ON publication_tags(tag_id);

CREATE TABLE IF NOT EXISTS publication_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    requester_email TEXT,
    title TEXT NOT NULL,
    year INTEGER,
    doi TEXT,
    url TEXT,
    venue TEXT,
    authors_text TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    submitted_at DATETIME,
    reviewed_at DATETIME,
    created_publication_id INTEGER,
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
    FOREIGN KEY (created_publication_id) REFERENCES publications(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_publication_requests_status ON publication_requests(status);
CREATE INDEX IF NOT EXISTS idx_publication_requests_member ON publication_requests(member_id);

CREATE TABLE IF NOT EXISTS publication_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    key_type TEXT NOT NULL,
    key_value TEXT NOT NULL,
    action TEXT NOT NULL,
    note TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    UNIQUE (member_id, key_type, key_value),
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_publication_overrides_member ON publication_overrides(member_id);

CREATE TABLE IF NOT EXISTS publication_match_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    year INTEGER,
    doi TEXT,
    arxiv_id TEXT,
    venue TEXT,
    authors_json TEXT,
    score REAL,
    score_breakdown_json TEXT,
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    match_reason TEXT,
    created_publication_id INTEGER,
    submitted_at DATETIME,
    reviewed_at DATETIME,
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
    FOREIGN KEY (created_publication_id) REFERENCES publications(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_match_candidates_status ON publication_match_candidates(status);
CREATE INDEX IF NOT EXISTS idx_match_candidates_member ON publication_match_candidates(member_id);
