"""Backward-compatible exports for the sync service."""
from services.sync_service import (
    sync_from_arxiv,
    sync_from_crossref,
    sync_from_openalex,
    sync_from_orcid,
)

__all__ = [
    "sync_from_orcid",
    "sync_from_openalex",
    "sync_from_crossref",
    "sync_from_arxiv",
]
