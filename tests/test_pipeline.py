"""Tests for ORCID-anchored tiered matching pipeline."""
import unittest
from types import SimpleNamespace
from unittest import mock

from services.orcid_client import _extract_external_ids, normalize_orcid
from services.openalex_client import work_has_orcid
from services.pipeline.dedupe import dedupe_records, record_keys
from services.pipeline.normalize import unify_record
from services.pipeline.overrides import (
    ACTION_ALLOW,
    ACTION_BLOCK,
    is_allowed,
    is_blocked,
    keys_for_record,
)
from services.pipeline.runner import run_for_member
from services.pipeline.scoring import passes_tier3_threshold, score_tier3_candidate


class OrcidExtractionTests(unittest.TestCase):
    def test_extracts_doi_and_arxiv(self):
        ids = _extract_external_ids(
            [
                {"external-id-type": "doi", "external-id-value": "https://doi.org/10.1/xyz"},
                {"external-id-type": "arxiv", "external-id-value": "2401.01234v2"},
            ]
        )
        self.assertEqual(ids["doi"], "10.1/xyz")
        self.assertEqual(ids["arxiv"], "2401.01234")

    def test_normalize_orcid(self):
        self.assertEqual(
            normalize_orcid("https://orcid.org/0000-0002-1825-0097"),
            "0000-0002-1825-0097",
        )


class OpenAlexOrcidVerifyTests(unittest.TestCase):
    def test_work_has_orcid(self):
        authorships = [
            {"author": {"orcid": "https://orcid.org/0000-0002-1825-0097", "display_name": "A"}},
            {"author": {"orcid": None, "display_name": "B"}},
        ]
        self.assertTrue(work_has_orcid(authorships, "0000-0002-1825-0097"))
        self.assertFalse(work_has_orcid(authorships, "0000-0001-0000-0000"))


class DedupeTests(unittest.TestCase):
    def test_priority_doi_arxiv_title_year(self):
        a = unify_record(
            {"title": "Hello World!", "year": 2024, "doi": "10.1/ABC", "source": "orcid"},
            tier=1,
            match_reason="orcid_claimed",
            source_name="orcid",
        )
        b = unify_record(
            {
                "title": "Hello World",
                "year": 2024,
                "arxiv_id": "2401.01234",
                "abstract": "Full abstract",
                "source": "openalex",
                "authors": [{"author_name": "Ada"}],
            },
            tier=2,
            match_reason="orcid_in_authorship",
            source_name="openalex",
        )
        # Same DOI wins even with different title punctuation once DOI present on both
        b["doi"] = "10.1/abc"
        merged = dedupe_records([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["doi"], "10.1/ABC")
        self.assertIn("orcid", merged[0]["sources"])
        self.assertIn("openalex", merged[0]["sources"])
        self.assertEqual(merged[0]["confidence_tier"], 1)

    def test_arxiv_key(self):
        record = {"arxiv_id": "2401.01234v3", "title": "X", "year": 2024}
        self.assertIn(("arxiv", "2401.01234"), record_keys(record))


class ScoringTests(unittest.TestCase):
    def test_coauthor_and_threshold(self):
        trusted = [
            {
                "title": "Trusted",
                "year": 2024,
                "authors": [
                    {"author_name": "Md Mahade Hasan"},
                    {"author_name": "Pekka Abrahamsson"},
                ],
                "concepts": [{"id": "C1", "display_name": "Software engineering"}],
            }
        ]
        candidate = {
            "title": "Candidate",
            "year": 2025,
            "authors": [
                {"author_name": "Mahade Hasan"},
                {"author_name": "Pekka Abrahamsson"},
            ],
            "concepts": [{"id": "C1", "display_name": "Software engineering"}],
            "affiliations": [{"name": "Tampere University", "ror": "https://ror.org/033003e23"}],
        }
        score, breakdown = score_tier3_candidate(
            candidate,
            trusted_records=trusted,
            member_name="Md Mahade Hasan",
            lab_member_names=["Md Mahade Hasan", "Pekka Abrahamsson"],
        )
        self.assertGreater(breakdown["coauthor_overlap"], 0)
        self.assertEqual(breakdown["affiliation_match"], 1.0)
        self.assertTrue(passes_tier3_threshold(score, threshold=0.5))

    def test_homonym_medical_paper_low_without_signals(self):
        trusted = [
            {
                "title": "Haskell Refactoring",
                "year": 2025,
                "authors": [
                    {"author_name": "Md Mahade Hasan"},
                    {"author_name": "Muhammad Waseem"},
                ],
                "concepts": [{"display_name": "Software engineering"}],
            }
        ]
        candidate = {
            "title": "Predicting Diabetes",
            "year": 2010,
            "authors": [
                {"author_name": "Mahade Hasan"},
                {"author_name": "Farhana Yasmin"},
            ],
            "concepts": [{"display_name": "Medicine"}],
            "affiliations": [],
        }
        score, _ = score_tier3_candidate(
            candidate,
            trusted_records=trusted,
            member_name="Md Mahade Hasan",
            lab_member_names=["Md Mahade Hasan", "Muhammad Waseem"],
            career_year_min=2020,
            career_year_max=2026,
        )
        self.assertFalse(passes_tier3_threshold(score, threshold=0.7))


class OverrideLogicTests(unittest.TestCase):
    def test_keys_for_record(self):
        keys = keys_for_record({"doi": "10.1/X", "arxiv_id": "2401.00001v1"})
        self.assertEqual(keys, [("doi", "10.1/x"), ("arxiv", "2401.00001")])

    def test_block_beats_allow_maps(self):
        record = {"doi": "10.1/x", "title": "T"}
        mapping = {("doi", "10.1/x"): ACTION_BLOCK}
        self.assertTrue(is_blocked(record, 1, mapping))
        self.assertFalse(is_allowed(record, 1, mapping))
        mapping = {("doi", "10.1/x"): ACTION_ALLOW}
        self.assertTrue(is_allowed(record, 1, mapping))


class RunnerTests(unittest.TestCase):
    def test_missing_orcid_rejects(self):
        member = SimpleNamespace(id=1, name="Ada", orcid=None)
        result = run_for_member(member)
        self.assertEqual(result["accepted"], [])
        self.assertEqual(result["decisions_log"][0]["reason"], "missing_orcid")

    def test_tier3_never_auto_accepted(self):
        member = SimpleNamespace(id=1, name="Md Mahade Hasan", orcid="0000-0002-1825-0097")

        tier1 = [
            unify_record(
                {
                    "title": "Lab Paper",
                    "year": 2025,
                    "doi": "10.1/lab",
                    "authors": [
                        {"author_name": "Md Mahade Hasan"},
                        {"author_name": "Pekka Abrahamsson"},
                    ],
                    "source": "orcid",
                },
                tier=1,
                match_reason="orcid_claimed",
                orcid=member.orcid,
                source_name="orcid",
            )
        ]
        name_only = [
            {
                "title": "Diabetes Paper",
                "year": 2025,
                "doi": "10.1/diabetes",
                "authors": [
                    {"author_name": "Mahade Hasan"},
                    {"author_name": "Farhana Yasmin"},
                ],
                "concepts": [],
                "affiliations": [],
                "confidence_tier": 3,
                "sources": ["name"],
            }
        ]

        with mock.patch(
            "services.pipeline.runner.orcid_fetch.fetch_tier1_works", return_value=tier1
        ), mock.patch(
            "services.pipeline.runner.openalex_fetch.fetch_tier2_works",
            return_value=([], []),
        ), mock.patch(
            "services.pipeline.runner.arxiv_enrich.enrich_records_with_arxiv",
            side_effect=lambda records: records,
        ), mock.patch(
            "services.pipeline.runner.arxiv_name_candidates.fetch_arxiv_name_candidates",
            return_value=[],
        ), mock.patch(
            "services.pipeline.runner.override_maps", return_value={}
        ):
            result = run_for_member(
                member,
                lab_member_names=["Md Mahade Hasan", "Pekka Abrahamsson"],
                include_name_candidates=name_only,
            )

        accepted_titles = {item["title"] for item in result["accepted"]}
        self.assertIn("Lab Paper", accepted_titles)
        self.assertNotIn("Diabetes Paper", accepted_titles)
        # Either queued or rejected — never in accepted
        self.assertTrue(
            any(item.get("title") == "Diabetes Paper" for item in result["needs_review"])
            or any(
                item.get("title") == "Diabetes Paper" and item.get("action") == "reject"
                for item in result["decisions_log"]
            )
        )

    def test_blocklist_beats_tier1(self):
        member = SimpleNamespace(id=1, name="Ada", orcid="0000-0002-1825-0097")
        tier1 = [
            unify_record(
                {"title": "Blocked Work", "year": 2024, "doi": "10.1/blocked", "source": "orcid"},
                tier=1,
                match_reason="orcid_claimed",
                orcid=member.orcid,
                source_name="orcid",
            )
        ]
        with mock.patch(
            "services.pipeline.runner.orcid_fetch.fetch_tier1_works", return_value=tier1
        ), mock.patch(
            "services.pipeline.runner.openalex_fetch.fetch_tier2_works",
            return_value=([], []),
        ), mock.patch(
            "services.pipeline.runner.arxiv_enrich.enrich_records_with_arxiv",
            side_effect=lambda records: records,
        ), mock.patch(
            "services.pipeline.runner.arxiv_name_candidates.fetch_arxiv_name_candidates",
            return_value=[],
        ), mock.patch(
            "services.pipeline.runner.override_maps",
            return_value={("doi", "10.1/blocked"): ACTION_BLOCK},
        ):
            result = run_for_member(member)
        self.assertEqual(result["accepted"], [])
        self.assertTrue(
            any(item.get("reason") == "manual_blocklist" for item in result["decisions_log"])
        )

    def test_allowlist_promotes_name_candidate(self):
        member = SimpleNamespace(id=1, name="Ada", orcid="0000-0002-1825-0097")
        name_only = [
            {
                "title": "Allowed Solo",
                "year": 2024,
                "doi": "10.1/allowed",
                "authors": [{"author_name": "Ada"}],
                "confidence_tier": 3,
                "sources": ["name"],
            }
        ]
        with mock.patch(
            "services.pipeline.runner.orcid_fetch.fetch_tier1_works", return_value=[]
        ), mock.patch(
            "services.pipeline.runner.openalex_fetch.fetch_tier2_works",
            return_value=([], []),
        ), mock.patch(
            "services.pipeline.runner.arxiv_enrich.enrich_records_with_arxiv",
            side_effect=lambda records: records,
        ), mock.patch(
            "services.pipeline.runner.arxiv_name_candidates.fetch_arxiv_name_candidates",
            return_value=[],
        ), mock.patch(
            "services.pipeline.runner.override_maps",
            return_value={("doi", "10.1/allowed"): ACTION_ALLOW},
        ):
            result = run_for_member(member, include_name_candidates=name_only)
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["accepted"][0]["match_reason"], "manual_allowlist")

    def test_arxiv_name_hits_go_to_review_never_accepted(self):
        member = SimpleNamespace(id=1, name="Md Mahade Hasan", orcid="0000-0002-1825-0097")
        tier1 = [
            unify_record(
                {
                    "title": "Trusted Lab Paper",
                    "year": 2025,
                    "doi": "10.1/trusted",
                    "authors": [
                        {"author_name": "Md Mahade Hasan"},
                        {"author_name": "Pekka Abrahamsson"},
                    ],
                    "source": "orcid",
                },
                tier=1,
                match_reason="orcid_claimed",
                orcid=member.orcid,
                source_name="orcid",
            )
        ]
        arxiv_hit = unify_record(
            {
                "title": "New Preprint With Lab Coauthor",
                "year": 2025,
                "arxiv_id": "2501.12345",
                "authors": [
                    {"author_name": "Md Mahade Hasan"},
                    {"author_name": "Pekka Abrahamsson"},
                ],
                "source": "arxiv",
                "is_preprint": True,
            },
            tier=3,
            match_reason="arxiv_name_exact",
            source_name="arxiv",
        )

        with mock.patch(
            "services.pipeline.runner.orcid_fetch.fetch_tier1_works", return_value=tier1
        ), mock.patch(
            "services.pipeline.runner.openalex_fetch.fetch_tier2_works",
            return_value=([], []),
        ), mock.patch(
            "services.pipeline.runner.arxiv_enrich.enrich_records_with_arxiv",
            side_effect=lambda records: records,
        ), mock.patch(
            "services.pipeline.runner.arxiv_name_candidates.fetch_arxiv_name_candidates",
            return_value=[arxiv_hit],
        ), mock.patch(
            "services.pipeline.runner.config.ARXIV_NAME_CANDIDATES_ENABLED", True
        ), mock.patch(
            "services.pipeline.runner.override_maps", return_value={}
        ):
            result = run_for_member(
                member,
                lab_member_names=["Md Mahade Hasan", "Pekka Abrahamsson"],
            )

        accepted_titles = {item["title"] for item in result["accepted"]}
        self.assertIn("Trusted Lab Paper", accepted_titles)
        self.assertNotIn("New Preprint With Lab Coauthor", accepted_titles)
        self.assertTrue(
            any(
                item.get("title") == "New Preprint With Lab Coauthor"
                for item in result["needs_review"]
            )
        )
        self.assertTrue(
            any(
                item.get("reason") == "arxiv_name_exact"
                and item.get("action") == "fetch"
                for item in result["decisions_log"]
            )
        )

    def test_arxiv_name_scores_with_known_coauthors_without_db_roster(self):
        """Cold-start member: empty ORCID, but papers list Pekka → review queue."""
        member = SimpleNamespace(id=5, name="Md Aidul Islam", orcid="0009-0003-9441-2371")
        arxiv_hit = unify_record(
            {
                "title": "AI Sandbox: Technical Report",
                "year": 2026,
                "arxiv_id": "2608.02679",
                "authors": [
                    {"author_name": "Muhammad Waseem"},
                    {"author_name": "Md Aidul Islam"},
                    {"author_name": "Pekka Abrahamsson"},
                ],
                "source": "arxiv",
                "is_preprint": True,
            },
            tier=3,
            match_reason="arxiv_name_exact",
            source_name="arxiv",
        )
        with mock.patch(
            "services.pipeline.runner.orcid_fetch.fetch_tier1_works", return_value=[]
        ), mock.patch(
            "services.pipeline.runner.openalex_fetch.fetch_tier2_works",
            return_value=([], []),
        ), mock.patch(
            "services.pipeline.runner.arxiv_enrich.enrich_records_with_arxiv",
            side_effect=lambda records: records,
        ), mock.patch(
            "services.pipeline.runner.arxiv_name_candidates.fetch_arxiv_name_candidates",
            return_value=[arxiv_hit],
        ), mock.patch(
            "services.pipeline.runner.config.ARXIV_NAME_CANDIDATES_ENABLED", True
        ), mock.patch(
            "services.pipeline.runner.override_maps", return_value={}
        ):
            # Empty DB roster — known coauthors come from config merge.
            result = run_for_member(member, lab_member_names=[])

        self.assertEqual(result["accepted"], [])
        self.assertEqual(len(result["needs_review"]), 1)
        self.assertEqual(result["needs_review"][0]["arxiv_id"], "2608.02679")
        self.assertGreaterEqual(result["needs_review"][0]["score"], 0.7)

    def test_arxiv_name_skips_ids_already_in_tier1(self):
        from services.pipeline.arxiv_name_candidates import fetch_arxiv_name_candidates

        member_name = "Ada Lovelace"
        existing = [
            unify_record(
                {
                    "title": "Already Known",
                    "year": 2024,
                    "arxiv_id": "2401.00001",
                    "authors": [{"author_name": "Ada Lovelace"}],
                    "source": "orcid",
                },
                tier=1,
                match_reason="orcid_claimed",
                source_name="orcid",
            )
        ]
        raw = [
            {
                "title": "Already Known",
                "year": 2024,
                "arxiv_id": "2401.00001",
                "authors": [{"author_name": "Ada Lovelace"}],
                "source": "arxiv",
            },
            {
                "title": "Brand New",
                "year": 2025,
                "arxiv_id": "2501.00002",
                "authors": [{"author_name": "Ada Lovelace"}],
                "source": "arxiv",
            },
            {
                "title": "Wrong Person",
                "year": 2025,
                "arxiv_id": "2501.00003",
                "authors": [{"author_name": "A. Different"}],
                "source": "arxiv",
            },
        ]
        with mock.patch(
            "services.pipeline.arxiv_name_candidates.arxiv_client.fetch_works",
            return_value=raw,
        ) as fetch_mock:
            hits = fetch_arxiv_name_candidates(
                member_name, exclude_records=existing
            )

        fetch_mock.assert_called_once()
        query = fetch_mock.call_args[0][0]
        self.assertEqual(query, 'au:"Ada Lovelace"')
        titles = {item["title"] for item in hits}
        self.assertEqual(titles, {"Brand New"})
        self.assertEqual(hits[0]["match_reason"], "arxiv_name_exact")
        self.assertEqual(hits[0]["confidence_tier"], 3)


if __name__ == "__main__":
    unittest.main()
