"""Single entry point for ORCID-anchored tiered publication matching."""
import json

import config
from services.orcid_client import normalize_orcid
from services.pipeline import arxiv_enrich, arxiv_name_candidates, orcid_fetch, openalex_fetch
from services.pipeline.dedupe import dedupe_records, record_keys
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

    # Merge DB roster with configured known GPT Lab coauthors for Tier 3 scoring.
    lab_member_names = _merge_lab_names(lab_member_names)

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
        _route_tier3(
            record,
            member=member,
            lab_member_names=lab_member_names,
            trusted_records=accepted,
            needs_review=needs_review,
            decisions=decisions,
            mapping=mapping,
        )

    # Exact-name arXiv search → Tier 3 review only (never auto-import).
    name_candidates = list(include_name_candidates or [])
    if config.ARXIV_NAME_CANDIDATES_ENABLED:
        try:
            arxiv_hits = arxiv_name_candidates.fetch_arxiv_name_candidates(
                member.name,
                exclude_records=accepted + combined,
            )
            name_candidates.extend(arxiv_hits)
            for hit in arxiv_hits:
                decisions.append(
                    _decision("fetch", "arxiv_name_exact", hit, tier=3)
                )
        except Exception as exc:
            decisions.append(
                {
                    "action": "reject",
                    "reason": f"arxiv_name_fetch_failed:{exc}",
                    "title": None,
                    "tier": 3,
                    "score": None,
                    "threshold": config.TIER3_SCORE_THRESHOLD,
                }
            )

    # Dedupe name candidates against each other and against accepted.
    accepted_keys = set()
    for record in accepted:
        accepted_keys.update(record_keys(record))
    review_keys = set()
    for item in needs_review:
        review_keys.update(record_keys(item))

    seen_name_keys = set()
    for candidate in name_candidates:
        cand_keys = set(record_keys(candidate))
        if cand_keys and cand_keys.intersection(accepted_keys):
            decisions.append(
                _decision("reject", "already_accepted_tier12", candidate, tier=3)
            )
            continue
        if cand_keys and cand_keys.intersection(review_keys | seen_name_keys):
            decisions.append(
                _decision("reject", "duplicate_candidate", candidate, tier=3)
            )
            continue
        seen_name_keys.update(cand_keys)

        before_review = len(needs_review)
        before_accepted = len(accepted)
        _route_tier3(
            candidate,
            member=member,
            lab_member_names=lab_member_names,
            trusted_records=accepted,
            needs_review=needs_review,
            decisions=decisions,
            mapping=mapping,
        )
        if len(needs_review) > before_review:
            review_keys.update(record_keys(needs_review[-1]))
        if len(accepted) > before_accepted:
            accepted_keys.update(record_keys(accepted[-1]))

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


def _route_tier3(
    candidate,
    *,
    member,
    lab_member_names,
    trusted_records,
    needs_review,
    decisions,
    mapping,
):
    """Score a Tier 3 candidate; queue above threshold, never auto-accept (unless allowlisted)."""
    if is_blocked(candidate, member.id, mapping):
        decisions.append(_decision("reject", "manual_blocklist", candidate, tier=3))
        return
    if is_allowed(candidate, member.id, mapping):
        # Allowlist is handled for Tier 1/2 above; if a name hit is allowlisted,
        # promote it into accepted here.
        allowed = dict(candidate)
        allowed["match_reason"] = "manual_allowlist"
        allowed["confidence_tier"] = 2
        trusted_records.append(allowed)
        decisions.append(_decision("accept", "manual_allowlist", allowed, tier=2))
        return

    score, breakdown = score_tier3_candidate(
        candidate,
        trusted_records=trusted_records,
        member_name=member.name,
        lab_member_names=lab_member_names,
    )
    reviewed = dict(candidate)
    reviewed["confidence_tier"] = 3
    reviewed["score"] = score
    reviewed["score_breakdown"] = breakdown
    base_reason = reviewed.get("match_reason") or "tier3"
    reviewed["match_reason"] = f"{base_reason}|tier3_score:{score:.2f}"
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


def _merge_lab_names(lab_member_names):
    """Union archive members with config-known GPT Lab coauthors (deduped)."""
    merged = []
    seen = set()
    for name in list(lab_member_names or []) + list(config.LAB_KNOWN_COAUTHOR_NAMES or []):
        text = (name or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return merged
