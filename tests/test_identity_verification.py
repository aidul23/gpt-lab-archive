"""Tests for author matching and arXiv identity corroboration."""
import unittest

from services.author_matching import names_refer_to_same_person
from services.identity_verification import (
    arxiv_candidate_is_trusted,
    normalize_arxiv_id,
)


def _candidate(title, authors, source_id=None):
    return {
        "title": title,
        "source_id": source_id,
        "authors": [
            {"author_name": name, "author_position": index}
            for index, name in enumerate(authors, start=1)
        ],
    }


class AuthorMatchingTests(unittest.TestCase):
    def test_accepts_md_prefix_variant(self):
        self.assertTrue(
            names_refer_to_same_person("Mahade Hasan", "Md Mahade Hasan")
        )

    def test_rejects_extra_middle_name(self):
        self.assertFalse(
            names_refer_to_same_person(
                "Muhammad Danish Waseem", "Muhammad Waseem"
            )
        )


class IdentityVerificationTests(unittest.TestCase):
    def test_normalize_arxiv_id(self):
        self.assertEqual(normalize_arxiv_id("2505.07036v1"), "2505.07036")
        self.assertEqual(
            normalize_arxiv_id("http://arxiv.org/abs/2505.07036v1"), "2505.07036"
        )
        self.assertEqual(
            normalize_arxiv_id("10.48550/arXiv.2411.08507"), "2411.08507"
        )

    def test_rejects_homonym_without_corroboration(self):
        candidate = _candidate(
            "Predicting Diabetes Using Machine Learning",
            ["Mahade Hasan", "Farhana Yasmin"],
            source_id="2505.07036v1",
        )
        self.assertFalse(
            arxiv_candidate_is_trusted(
                candidate,
                "Md Mahade Hasan",
                known_coauthor_names=[
                    "Muhammad Waseem",
                    "Pekka Abrahamsson",
                    "Md Mahade Hasan",
                ],
                lab_member_names=["Md Mahade Hasan", "Muhammad Waseem"],
                known_arxiv_ids={"2411.08507"},
            )
        )

    def test_accepts_when_lab_coauthor_present(self):
        candidate = _candidate(
            "AI Sandbox: Technical Report",
            ["Muhammad Waseem", "Md Mahade Hasan", "Pekka Abrahamsson"],
            source_id="2501.00001v1",
        )
        self.assertTrue(
            arxiv_candidate_is_trusted(
                candidate,
                "Md Mahade Hasan",
                known_coauthor_names=[],
                lab_member_names=["Md Mahade Hasan", "Muhammad Waseem"],
                known_arxiv_ids=set(),
            )
        )

    def test_accepts_when_known_coauthor_overlaps(self):
        candidate = _candidate(
            "Some Preprint",
            ["Mahade Hasan", "Zeeshan Rasheed"],
            source_id="2501.00002",
        )
        self.assertTrue(
            arxiv_candidate_is_trusted(
                candidate,
                "Md Mahade Hasan",
                known_coauthor_names=["Zeeshan Rasheed", "Jussi Rasku"],
                lab_member_names=["Md Mahade Hasan"],
                known_arxiv_ids=set(),
            )
        )

    def test_accepts_known_arxiv_id(self):
        candidate = _candidate(
            "TimeLess",
            ["Md Mahade Hasan"],
            source_id="2411.08507v2",
        )
        self.assertTrue(
            arxiv_candidate_is_trusted(
                candidate,
                "Md Mahade Hasan",
                known_coauthor_names=[],
                lab_member_names=["Md Mahade Hasan"],
                known_arxiv_ids={"2411.08507"},
            )
        )

    def test_rejects_solo_author_without_known_id(self):
        candidate = _candidate(
            "Solo Ambiguous Preprint",
            ["Mahade Hasan"],
            source_id="2501.99999",
        )
        self.assertFalse(
            arxiv_candidate_is_trusted(
                candidate,
                "Md Mahade Hasan",
                known_coauthor_names=["Muhammad Waseem"],
                lab_member_names=["Md Mahade Hasan", "Muhammad Waseem"],
                known_arxiv_ids=set(),
            )
        )


if __name__ == "__main__":
    unittest.main()
