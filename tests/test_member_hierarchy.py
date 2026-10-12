"""Tests for member role hierarchy helpers."""
import unittest
from types import SimpleNamespace

from services.member_hierarchy import (
    MEMBER_ROLES,
    ROLE_POSTDOC,
    ROLE_PROFESSOR,
    build_hierarchy,
    normalize_role,
    would_create_cycle,
)


class RoleNormalizeTests(unittest.TestCase):
    def test_canonical_roles_stable(self):
        self.assertEqual(len(MEMBER_ROLES), 8)
        self.assertEqual(normalize_role("Postdoc"), ROLE_POSTDOC)
        self.assertEqual(normalize_role("PhD Student"), "Doctoral Researcher / PhD")
        self.assertEqual(normalize_role("Doctoral Student / PhD"), "Doctoral Researcher / PhD")
        self.assertEqual(normalize_role("University Lecturer"), "University Lecturer / Teacher")
        self.assertEqual(normalize_role("Principal Investigator"), ROLE_PROFESSOR)
        self.assertIsNone(normalize_role(""))


class HierarchyBuildTests(unittest.TestCase):
    def test_builds_tree_under_professor(self):
        pekka = SimpleNamespace(id=1, name="Pekka Abrahamsson", role=ROLE_PROFESSOR, reports_to_id=None)
        postdoc = SimpleNamespace(id=2, name="Post Doc", role=ROLE_POSTDOC, reports_to_id=1)
        phd = SimpleNamespace(id=3, name="PhD Student", role="Doctoral Researcher / PhD", reports_to_id=2)
        ra = SimpleNamespace(id=4, name="RA Person", role="Research Assistant", reports_to_id=2)

        forest = build_hierarchy([ra, phd, postdoc, pekka])
        self.assertEqual(len(forest["roots"]), 1)
        root = forest["roots"][0]
        self.assertEqual(root["member"].name, "Pekka Abrahamsson")
        self.assertEqual(len(root["children"]), 1)
        self.assertEqual(root["children"][0]["member"].name, "Post Doc")
        child_names = {c["member"].name for c in root["children"][0]["children"]}
        self.assertEqual(child_names, {"PhD Student", "RA Person"})

    def test_cycle_detection(self):
        a = SimpleNamespace(id=1, reports_to_id=2)
        b = SimpleNamespace(id=2, reports_to_id=1)
        by_id = {1: a, 2: b}
        self.assertTrue(would_create_cycle(1, 2, by_id))
        self.assertTrue(would_create_cycle(1, 1, by_id))
        c = SimpleNamespace(id=3, reports_to_id=None)
        by_id[3] = c
        self.assertFalse(would_create_cycle(2, 3, by_id))


if __name__ == "__main__":
    unittest.main()
