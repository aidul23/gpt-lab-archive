"""Tests for lab coauthor auto-link on Match Review approve."""
import unittest
from types import SimpleNamespace
from unittest import mock

from services.author_matching import names_refer_to_same_person
from services.publication_service import link_matching_lab_coauthors


class CoauthorAutoLinkTests(unittest.TestCase):
    def test_names_match_md_variants(self):
        self.assertTrue(
            names_refer_to_same_person("Md Mahade Hasan", "Md Mahade Hasan")
        )
        self.assertTrue(
            names_refer_to_same_person("MD Aidul Islam", "Md Aidul Islam")
        )

    def test_links_matching_coauthor_and_skips_blocked(self):
        aidul = SimpleNamespace(id=5, name="Md Aidul Islam")
        mahade = SimpleNamespace(id=6, name="Md Mahade Hasan")
        stranger = SimpleNamespace(id=7, name="Someone Else")

        authors = [
            SimpleNamespace(author_name="Md Aidul Islam", member_id=5),
            SimpleNamespace(author_name="Md Mahade Hasan", member_id=None),
            SimpleNamespace(author_name="Pekka Abrahamsson", member_id=None),
        ]
        publication = SimpleNamespace(
            id=42,
            title="Shared Paper",
            doi=None,
            arxiv_id="2608.02679",
            authors=authors,
        )
        record = {"arxiv_id": "2608.02679", "title": "Shared Paper"}

        def is_blocked(rec, member_id, mapping=None):
            return member_id == stranger.id

        with mock.patch(
            "services.member_service.get_all_members",
            return_value=[aidul, mahade, stranger],
        ), mock.patch(
            "services.pipeline.overrides.is_blocked",
            side_effect=is_blocked,
        ), mock.patch(
            "services.pipeline.overrides.allow_record_for_member"
        ) as allow_mock, mock.patch(
            "services.match_candidate_service.resolve_pending_for_record",
            return_value=0,
        ), mock.patch(
            "services.publication_service.db.session.commit"
        ):
            # Re-import path uses member_service inside the function
            linked = link_matching_lab_coauthors(
                publication,
                record,
                exclude_member_ids=[aidul.id],
            )

        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["name"], "Md Mahade Hasan")
        self.assertEqual(authors[1].member_id, mahade.id)
        allow_mock.assert_called_once()
        self.assertEqual(allow_mock.call_args[0][0], mahade.id)

    def test_does_not_steal_other_member_link(self):
        mahade = SimpleNamespace(id=6, name="Md Mahade Hasan")
        other = SimpleNamespace(id=8, name="Md Mahade Hasan")  # duplicate name edge case
        authors = [
            SimpleNamespace(author_name="Md Mahade Hasan", member_id=8),
        ]
        publication = SimpleNamespace(
            id=1,
            title="X",
            doi="10.1/x",
            arxiv_id=None,
            authors=authors,
        )
        with mock.patch(
            "services.member_service.get_all_members",
            return_value=[mahade, other],
        ), mock.patch(
            "services.pipeline.overrides.is_blocked",
            return_value=False,
        ), mock.patch(
            "services.pipeline.overrides.allow_record_for_member"
        ) as allow_mock, mock.patch(
            "services.match_candidate_service.resolve_pending_for_record",
            return_value=1,
        ), mock.patch(
            "services.publication_service.db.session.commit"
        ):
            linked = link_matching_lab_coauthors(
                publication,
                {"doi": "10.1/x"},
                exclude_member_ids=[],
            )

        # other already owns the row; mahade must not steal it
        self.assertEqual(linked, [])
        self.assertEqual(authors[0].member_id, 8)
        allow_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
