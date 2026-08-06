#!/usr/bin/env python3
"""CLI entry point for the ORCID-anchored publication pipeline."""
import argparse
import json
import sys

from app import create_app
from services import member_service
from services.pipeline import runner as pipeline_runner


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run ORCID-anchored tiered publication matching for a member."
    )
    parser.add_argument("--member-id", type=int, help="Member primary key")
    parser.add_argument("--orcid", help="ORCID to resolve a member, or run orphan dry-run")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print accepted + needs_review JSON",
    )
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        member = None
        if args.member_id:
            member = member_service.get_member_by_id(args.member_id)
        elif args.orcid:
            members = member_service.get_all_members_admin()
            bare = args.orcid.strip().lower().replace("https://orcid.org/", "")
            for item in members:
                if (item.orcid or "").lower().replace("https://orcid.org/", "") == bare:
                    member = item
                    break

        if not member:
            print("Member not found. Provide --member-id or a matching --orcid.", file=sys.stderr)
            return 1

        result = pipeline_runner.run_for_member(
            member,
            lab_member_names=[item.name for item in member_service.get_all_members()],
        )
        if args.json:
            print(pipeline_runner.records_to_json(result))
        else:
            print(f"Member: {member.name} ({member.orcid})")
            print(f"Accepted: {len(result['accepted'])}")
            print(f"Needs review: {len(result['needs_review'])}")
            print(f"Decisions: {len(result['decisions_log'])}")
            for decision in result["decisions_log"][:30]:
                print(
                    f"  [{decision['action']}] tier={decision.get('tier')} "
                    f"{decision.get('reason')}: {decision.get('title')}"
                )
            if len(result["decisions_log"]) > 30:
                print(f"  ... {len(result['decisions_log']) - 30} more")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
