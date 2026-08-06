"""Single entry point for ORCID-anchored tiered publication matching."""
import json

import config
from services.orcid_client import normalize_orcid
from services.pipeline import arxiv_enrich, orcid_fetch, openalex_fetch
from services.pipeline.dedupe import dedupe_records
from services.pipeline.overrides import is_allowed, is_blocked, override_maps
from services.pipeline.records import author_names, to_import_candidate
from services.pipeline.scoring import passes_tier3_threshold, score_tier3_candidate


def run_for_member(member, *, lab_member_names=None, include_name_candidates=None):
    """
    Run the tiered matcher for one researcher.

    Returns:
      {
        accepted: [unified records for auto-import],
        needs_review: [Tier 3 scored records],
        decisions_log: [{action, reason, title, tier, ...}],
        observed_openalex_author_ids: [...],
        json_accepted / json_review for CLI dump
      }

    Never auto-includes Tier 3. Blocklist always wins.
    """
    decisions = []
    orcid = normalize_orcid(getattr(member, "orcid", None))
    if not orcid:
        return {
            "accepted": [],
            "needs_review": [],
            "decisions_log": [
                {
                    "action": "reject",
                    "reason": "missing_orcid",
                    "title": None,
                    "tier": None,
                }
            ],
            "observed_openalex_author_ids": [],
        }

    mapping = override_maps(member.id)

    tier1 = orcid_fetch.fetch_tier1_works(orcid)
    for record in tier1:
        decisions.append(_decision("fetch", "orcid_claimed", record, tier=1))

    tier2, observed_ids = openalex_fetch.fetch_tier2_works(orcid)
    for record in tier2:
        decisions.append(_decision("fetch", "orcid_in_authorship", record, tier=2))

    combined = dedupe_records(tier1 + tier2)
    combined = arxiv_enrich.enrich_records_with_arxiv(combined)
    combined = dedupe_records(combined)

    accepted = []
    needs_review = []

    for record in combined:
        title = record.get("title")
        if is_blocked(record, member.id, mapping):
            decisions.append(
                _decision("reject", "manual_blocklist", record, tier=record.get("confidence_tier"))
            )
            continue

        if is_allowed(record, member.id, mapping):
            record = dict(record)
            record["match_reason"] = "manual_allowlist"
            # Allowlist forces include even if originally Tier 3-shaped.
            if record.get("confidence_tier") is None or record.get("confidence_tier") > 2:
                record["confidence_tier"] = 2
            accepted.append(record)
            decisions.append(_decision("accept", "manual_allowlist", record, tier=record.get("confidence_tier")))
            continue

        tier = record.get("confidence_tier")
        if tier in (1, 2):
            accepted.append(record)
            decisions.append(
                _decision("accept", record.get("match_reason"), record, tier=tier)
            )
            continue

        # Unexpected non-tiered record: treat as Tier 3.
        score, breakdown = score_tier3_candidate(
            record,
            trusted_records=accepted,
            member_name=member.name,
            lab_member_names=lab_member_names,
        )
        record = dict(record)
        record["confidence_tier"] = 3
        record["score"] = score
        record["score_breakdown"] = breakdown
        record["match_reason"] = f"tier3_score:{score:.2f}"
        if passes_tier3_threshold(score):
            needs_review.append(record)
            decisions.append(
                _decision("review", record["match_reason"], record, tier=3, score=score)
            )
        else:
            decisions.append(
                _decision("reject", f"below_threshold:{score:.2f}", record, tier=3, score=score)
            )

    # Optional name-only candidates (future / tests). Never auto-accepted.
    for candidate in include_name_candidates or []:
        if is_blocked(candidate, member.id, mapping):
            decisions.append(_decision("reject", "manual_blocklist", candidate, tier=3))
            continue
        if is_allowed(candidate, member.id, mapping):
            allowed = dict(candidate)
            allowed["match_reason"] = "manual_allowlist"
            allowed["confidence_tier"] = 2
            accepted.append(allowed)
            decisions.append(_decision("accept", "manual_allowlist", allowed, tier=2))
            continue

        score, breakdown = score_tier3_candidate(
            candidate,
            trusted_records=accepted,
            member_name=member.name,
            lab_member_names=lab_member_names,
        )
        reviewed = dict(candidate)
        reviewed["confidence_tier"] = 3
        reviewed["score"] = score
        reviewed["score_breakdown"] = breakdown
        reviewed["match_reason"] = f"tier3_score:{score:.2f}"
        if passes_tier3_threshold(score):
            needs_review.append(reviewed)
            decisions.append(
                _decision("review", reviewed["match_reason"], reviewed, tier=3, score=score)
            )
        else:
            decisions.append(
                _decision(
                    "reject",
                    f"below_threshold:{score:.2f}",
                    reviewed,
                    tier=3,
                    score=score,
                )
            )

    return {
        "accepted": accepted,
        "needs_review": needs_review,
        "decisions_log": decisions,
        "observed_openalex_author_ids": observed_ids,
        "export": {
            "accepted": [_public_record(item) for item in accepted],
            "needs_review": [_public_record(item) for item in needs_review],
        },
    }


def records_to_json(result):
    """Serialize runner output for CLI / debugging."""
    return json.dumps(result.get("export") or {}, indent=2, ensure_ascii=False)


def importable_from_accepted(accepted_records):
    """Convert accepted unified records to publication_service candidates."""
    return [to_import_candidate(record) for record in accepted_records]


def _public_record(record):
    return {
        "title": record.get("title"),
        "authors": author_names(record),
        "year": record.get("year"),
        "doi": record.get("doi"),
        "arxiv_id": record.get("arxiv_id"),
        "venue": record.get("venue"),
        "type": record.get("type"),
        "url": record.get("url"),
        "matched_researcher_orcids": record.get("matched_researcher_orcids") or [],
        "confidence_tier": record.get("confidence_tier"),
        "match_reason": record.get("match_reason"),
        "sources": record.get("sources") or [],
        "score": record.get("score"),
        "score_breakdown": record.get("score_breakdown"),
    }


def _decision(action, reason, record, tier=None, score=None):
    return {
        "action": action,
        "reason": reason,
        "title": (record or {}).get("title"),
        "doi": (record or {}).get("doi"),
        "arxiv_id": (record or {}).get("arxiv_id"),
        "tier": tier,
        "score": score,
        "threshold": config.TIER3_SCORE_THRESHOLD if tier == 3 else None,
    }
