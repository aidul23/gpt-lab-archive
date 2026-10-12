"""Member roles and reporting hierarchy helpers."""

# Canonical role labels shown in selectors and on public pages.
ROLE_SUMMER_TRAINEE = "Summer Trainee"
ROLE_INTERN = "Intern"
ROLE_RESEARCH_ASSISTANT = "Research Assistant"
ROLE_PROJECT_RESEARCHER = "Project Researcher"
ROLE_DOCTORAL = "Doctoral Researcher / PhD"
ROLE_POSTDOC = "Postdoctoral Researcher"
ROLE_LECTURER = "University Lecturer / Teacher"
ROLE_PROFESSOR = "Professor"

MEMBER_ROLES = (
    ROLE_SUMMER_TRAINEE,
    ROLE_INTERN,
    ROLE_RESEARCH_ASSISTANT,
    ROLE_PROJECT_RESEARCHER,
    ROLE_DOCTORAL,
    ROLE_POSTDOC,
    ROLE_LECTURER,
    ROLE_PROFESSOR,
)

# Lower number = higher in the org chart.
ROLE_RANK = {
    ROLE_PROFESSOR: 0,
    ROLE_LECTURER: 1,
    ROLE_POSTDOC: 2,
    ROLE_DOCTORAL: 3,
    ROLE_PROJECT_RESEARCHER: 4,
    ROLE_RESEARCH_ASSISTANT: 5,
    ROLE_INTERN: 6,
    ROLE_SUMMER_TRAINEE: 7,
}

# Free-text legacy values → canonical role.
_ROLE_ALIASES = {
    "summer trainee": ROLE_SUMMER_TRAINEE,
    "trainee": ROLE_SUMMER_TRAINEE,
    "intern": ROLE_INTERN,
    "interns": ROLE_INTERN,
    "internship": ROLE_INTERN,
    "research assistant": ROLE_RESEARCH_ASSISTANT,
    "ra": ROLE_RESEARCH_ASSISTANT,
    "project researcher": ROLE_PROJECT_RESEARCHER,
    "doctoral student": ROLE_DOCTORAL,
    "doctoral student / phd": ROLE_DOCTORAL,
    "doctoral researcher": ROLE_DOCTORAL,
    "doctoral researcher / phd": ROLE_DOCTORAL,
    "phd": ROLE_DOCTORAL,
    "phd student": ROLE_DOCTORAL,
    "doctoral": ROLE_DOCTORAL,
    "post doctoral": ROLE_POSTDOC,
    "postdoctoral": ROLE_POSTDOC,
    "postdoctoral researcher": ROLE_POSTDOC,
    "postdoc": ROLE_POSTDOC,
    "post doc": ROLE_POSTDOC,
    "university lecturer / teacher": ROLE_LECTURER,
    "university lecturer/teacher": ROLE_LECTURER,
    "university lecturer": ROLE_LECTURER,
    "lecturer": ROLE_LECTURER,
    "teacher": ROLE_LECTURER,
    "professor": ROLE_PROFESSOR,
    "principal investigator": ROLE_PROFESSOR,
    "pi": ROLE_PROFESSOR,
}


def normalize_role(value):
    """Return a canonical role label, or None if empty/unknown."""
    text = (value or "").strip()
    if not text:
        return None
    if text in MEMBER_ROLES:
        return text
    return _ROLE_ALIASES.get(text.casefold())


def role_rank(role):
    """Sort key for hierarchy display (unknown roles sink to the bottom)."""
    canonical = normalize_role(role) or role
    if canonical in ROLE_RANK:
        return ROLE_RANK[canonical]
    return 50


def parse_reports_to_id(value):
    """Parse reports_to form value to int or None."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_hierarchy(members):
    """
    Build a forest of member nodes for the public members page.

    Returns:
      {
        roots: [node, ...],          # members with no supervisor (or orphaned FK)
        unassigned: [member, ...],   # same as roots without children, for flat fallback
        by_id: {id: node}
      }

    Each node: {member, children: [node, ...]}
    """
    members = list(members or [])
    by_id = {
        member.id: {"member": member, "children": []}
        for member in members
    }
    member_ids = set(by_id)

    roots = []
    for member in members:
        node = by_id[member.id]
        supervisor_id = member.reports_to_id
        if supervisor_id and supervisor_id in member_ids and supervisor_id != member.id:
            by_id[supervisor_id]["children"].append(node)
        else:
            roots.append(node)

    def _sort_nodes(nodes):
        nodes.sort(
            key=lambda item: (
                role_rank(item["member"].role),
                (item["member"].name or "").casefold(),
            )
        )
        for child in nodes:
            _sort_nodes(child["children"])

    _sort_nodes(roots)
    return {"roots": roots, "by_id": by_id}


def would_create_cycle(member_id, reports_to_id, members_by_id):
    """Return True if setting reports_to would create a cycle."""
    if not reports_to_id:
        return False
    if member_id and reports_to_id == member_id:
        return True
    seen = set()
    current = reports_to_id
    while current:
        if member_id and current == member_id:
            return True
        if current in seen:
            return True
        seen.add(current)
        supervisor = members_by_id.get(current)
        if not supervisor:
            break
        current = supervisor.reports_to_id
    return False
