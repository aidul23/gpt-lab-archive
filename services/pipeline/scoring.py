"""Tier 3 confidence scoring for name-only candidates (review queue only)."""
from services.author_matching import names_refer_to_same_person
from services.pipeline.records import author_names

import config


def score_tier3_candidate(
    candidate,
    *,
    trusted_records,
    member_name=None,
    lab_member_names=None,
    career_year_min=None,
    career_year_max=None,
):
    """
    Score a Tier 3 candidate against trusted Tier 1/2 work.

    Returns (score 0..1, breakdown dict). Never auto-publishes; caller routes
    scores >= threshold to the review queue.
    """
    breakdown = {
        "coauthor_overlap": 0.0,
        "affiliation_match": 0.0,
        "topic_similarity": 0.0,
        "timeline_plausibility": 0.0,
    }

    breakdown["coauthor_overlap"] = _coauthor_overlap_score(
        candidate, trusted_records, member_name=member_name, lab_member_names=lab_member_names
    )
    breakdown["affiliation_match"] = _affiliation_score(candidate)
    breakdown["topic_similarity"] = _topic_similarity_score(candidate, trusted_records)
    breakdown["timeline_plausibility"] = _timeline_score(
        candidate,
        trusted_records,
        career_year_min=career_year_min,
        career_year_max=career_year_max,
    )

    # Weighted combination — co-author overlap is the strongest signal.
    score = (
        0.45 * breakdown["coauthor_overlap"]
        + 0.25 * breakdown["affiliation_match"]
        + 0.20 * breakdown["topic_similarity"]
        + 0.10 * breakdown["timeline_plausibility"]
    )
    return round(score, 4), breakdown


def passes_tier3_threshold(score, threshold=None):
    """Return True when score meets the configurable review threshold."""
    if threshold is None:
        threshold = config.TIER3_SCORE_THRESHOLD
    return score is not None and score >= float(threshold)


def _coauthor_overlap_score(candidate, trusted_records, member_name=None, lab_member_names=None):
    candidate_authors = [
        name
        for name in author_names(candidate)
        if not (member_name and names_refer_to_same_person(name, member_name))
    ]
    if not candidate_authors:
        return 0.0

    trusted_coauthors = []
    for record in trusted_records or []:
        for name in author_names(record):
            if member_name and names_refer_to_same_person(name, member_name):
                continue
            trusted_coauthors.append(name)

    lab_names = [name for name in (lab_member_names or []) if name]
    hits = 0
    for author_name in candidate_authors:
        if any(
            names_refer_to_same_person(author_name, known)
            for known in trusted_coauthors
        ):
            hits += 1
            continue
        if any(
            names_refer_to_same_person(author_name, lab_name)
            for lab_name in lab_names
            if not (member_name and names_refer_to_same_person(lab_name, member_name))
        ):
            hits += 1

    if not candidate_authors:
        return 0.0
    return min(1.0, hits / max(1, min(3, len(candidate_authors))))


def _affiliation_score(candidate):
    affiliations = candidate.get("affiliations") or []
    if not affiliations:
        return 0.0

    keywords = [item.lower() for item in config.LAB_AFFILIATION_KEYWORDS]
    ror_ids = {item.lower().rstrip("/") for item in config.LAB_ROR_IDS}

    for affiliation in affiliations:
        if isinstance(affiliation, dict):
            text = " ".join(
                str(affiliation.get(key) or "")
                for key in ("name", "display_name", "ror", "id")
            ).lower()
            ror = str(affiliation.get("ror") or affiliation.get("id") or "").lower().rstrip("/")
        else:
            text = str(affiliation).lower()
            ror = ""
        if ror and ror in ror_ids:
            return 1.0
        if any(keyword in text for keyword in keywords):
            return 1.0
    return 0.0


def _topic_similarity_score(candidate, trusted_records):
    candidate_concepts = {
        (concept.get("id") or concept.get("display_name") or "").lower()
        for concept in (candidate.get("concepts") or [])
        if isinstance(concept, dict)
    }
    candidate_concepts |= {
        str(concept).lower()
        for concept in (candidate.get("concepts") or [])
        if not isinstance(concept, dict)
    }
    candidate_concepts.discard("")
    if not candidate_concepts:
        return 0.0

    trusted_concepts = set()
    for record in trusted_records or []:
        for concept in record.get("concepts") or []:
            if isinstance(concept, dict):
                key = (concept.get("id") or concept.get("display_name") or "").lower()
            else:
                key = str(concept).lower()
            if key:
                trusted_concepts.add(key)

    if not trusted_concepts:
        return 0.0
    overlap = candidate_concepts.intersection(trusted_concepts)
    return min(1.0, len(overlap) / max(1, min(5, len(candidate_concepts))))


def _timeline_score(candidate, trusted_records, career_year_min=None, career_year_max=None):
    year = candidate.get("year")
    if not year:
        return 0.5

    years = [record.get("year") for record in (trusted_records or []) if record.get("year")]
    min_year = career_year_min if career_year_min is not None else config.MEMBER_CAREER_YEAR_MIN
    max_year = career_year_max if career_year_max is not None else config.MEMBER_CAREER_YEAR_MAX

    if years:
        min_year = min(years) - 2 if min_year is None else min_year
        max_year = max(years) + 2 if max_year is None else max_year

    if min_year is None and max_year is None:
        return 0.5
    if min_year is not None and year < min_year:
        return 0.0
    if max_year is not None and year > max_year:
        return 0.0
    return 1.0
