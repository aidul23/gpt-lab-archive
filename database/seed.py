"""Seed the database with sample lab members and publications."""
import os
import sys

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask

import config
from database.db import Member, Publication, PublicationAuthor, PublicationTag, Tag, db, init_db


def create_app():
    """Create a minimal Flask app for seeding."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{config.DATABASE_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    init_db(app)
    return app


def seed():
    """Populate the database with sample data."""
    app = create_app()

    with app.app_context():
        # Reset database for repeatable seeding
        db.drop_all()
        db.create_all()

        members = [
            Member(
                name="Dr. Elena Vasquez",
                role="Principal Investigator",
                email="e.vasquez@example.edu",
                orcid="0000-0001-2345-6789",
                openalex_author_id="A1234567890",
                profile_url="https://example.edu/faculty/vasquez",
                photo_url="https://ui-avatars.com/api/?name=Elena+Vasquez&size=256&background=1e3a5f&color=ffffff&bold=true",
                bio=(
                    "Principal investigator leading research at the intersection of machine learning, "
                    "experimental design, and computational science."
                ),
                active=True,
                approval_status="approved",
                is_self_registered=False,
            ),
            Member(
                name="James Chen",
                role="Postdoctoral Researcher",
                email="j.chen@example.edu",
                orcid="0000-0002-3456-7890",
                openalex_author_id="A2345678901",
                profile_url="https://example.edu/people/chen",
                photo_url="https://ui-avatars.com/api/?name=James+Chen&size=256&background=2c5282&color=ffffff&bold=true",
                bio=(
                    "Postdoctoral researcher working on representation learning, cryo-EM analysis, "
                    "and scalable Bayesian optimization."
                ),
                active=True,
                approval_status="approved",
                is_self_registered=False,
            ),
            Member(
                name="Priya Sharma",
                role="PhD Student",
                email="p.sharma@example.edu",
                orcid="0000-0003-4567-8901",
                openalex_author_id="A3456789012",
                profile_url="https://example.edu/people/sharma",
                photo_url="https://ui-avatars.com/api/?name=Priya+Sharma&size=256&background=c4a35a&color=1e3a5f&bold=true",
                bio=(
                    "PhD student focused on benchmark datasets, molecular modeling, and neural potentials "
                    "for chemistry applications."
                ),
                active=True,
                approval_status="approved",
                is_self_registered=False,
            ),
            Member(
                name="Marcus Webb",
                role="Research Assistant",
                email="m.webb@example.edu",
                orcid="0000-0004-5678-9012",
                openalex_author_id="A4567890123",
                profile_url="https://example.edu/people/webb",
                bio="Former research assistant who contributed to active learning and screening projects.",
                active=False,
                approval_status="approved",
                is_self_registered=False,
            ),
        ]
        db.session.add_all(members)
        db.session.flush()

        elena, james, priya, marcus = members

        themes = [
            Tag(name="Machine Learning", slug="machine-learning", kind="theme",
                description="Methods and applications of machine learning in scientific research."),
            Tag(name="Computational Chemistry", slug="computational-chemistry", kind="theme",
                description="Simulation, modeling, and data-driven chemistry research."),
            Tag(name="Experimental Design", slug="experimental-design", kind="theme",
                description="Active learning, optimization, and lab automation."),
        ]
        tags = [
            Tag(name="Benchmark", slug="benchmark", kind="tag",
                description="Benchmark datasets or evaluation studies."),
            Tag(name="Collaboration", slug="collaboration", kind="tag",
                description="Multi-member or external collaborations."),
            Tag(name="Methods", slug="methods", kind="tag",
                description="Methodological contributions."),
        ]
        db.session.add_all(themes + tags)
        db.session.flush()

        theme_ml, theme_chem, theme_design = themes
        tag_benchmark, tag_collab, tag_methods = tags

        publications_data = [
            {
                "publication": Publication(
                    title="Graph Neural Networks for Molecular Property Prediction",
                    abstract=(
                        "We present a graph neural network architecture tailored for "
                        "predicting molecular properties from sparse chemical graphs."
                    ),
                    year=2024,
                    publication_date="2024-06-15",
                    type="article",
                    venue="Journal of Computational Chemistry",
                    doi="10.1000/example.2024.001",
                    url="https://doi.org/10.1000/example.2024.001",
                    pdf_url="https://example.edu/papers/gnn-molecules.pdf",
                    source="crossref",
                    source_id="10.1000/example.2024.001",
                    is_preprint=False,
                    is_published=True,
                    is_visible=True,
                ),
                "authors": [
                    (elena, "Dr. Elena Vasquez", 1),
                    (james, "James Chen", 2),
                    (priya, "Priya Sharma", 3),
                ],
                "tags": [theme_ml, tag_methods],
            },
            {
                "publication": Publication(
                    title="Scalable Bayesian Optimization for Experimental Design",
                    abstract=(
                        "A scalable framework for Bayesian optimization in high-throughput "
                        "laboratory settings with noisy measurements."
                    ),
                    year=2023,
                    publication_date="2023-11-02",
                    type="conference",
                    venue="NeurIPS 2023",
                    doi="10.1000/example.2023.002",
                    url="https://doi.org/10.1000/example.2023.002",
                    pdf_url="https://example.edu/papers/bo-experimental-design.pdf",
                    source="openalex",
                    source_id="W1234567890",
                    is_preprint=False,
                    is_published=True,
                    is_visible=True,
                ),
                "authors": [
                    (elena, "Dr. Elena Vasquez", 1),
                    (james, "James Chen", 2),
                ],
                "tags": [theme_design, theme_ml, tag_methods],
            },
            {
                "publication": Publication(
                    title="A Benchmark Dataset for Protein-Ligand Binding Affinity",
                    abstract=(
                        "We release a curated benchmark dataset and evaluation protocol "
                        "for protein-ligand binding affinity prediction."
                    ),
                    year=2023,
                    publication_date="2023-03-20",
                    type="dataset",
                    venue="Scientific Data",
                    doi="10.1000/example.2023.003",
                    url="https://doi.org/10.1000/example.2023.003",
                    pdf_url=None,
                    source="crossref",
                    source_id="10.1000/example.2023.003",
                    is_preprint=False,
                    is_published=True,
                    is_visible=True,
                ),
                "authors": [
                    (priya, "Priya Sharma", 1),
                    (marcus, "Marcus Webb", 2),
                    (elena, "Dr. Elena Vasquez", 3),
                ],
                "tags": [theme_chem, tag_benchmark, tag_collab],
            },
            {
                "publication": Publication(
                    title="Self-Supervised Representation Learning for Cryo-EM Volumes",
                    abstract=(
                        "Preprint describing a self-supervised approach for learning "
                        "representations from cryo-EM density maps."
                    ),
                    year=2024,
                    publication_date="2024-09-01",
                    type="article",
                    venue="arXiv",
                    doi=None,
                    url="https://arxiv.org/abs/2409.01234",
                    pdf_url="https://arxiv.org/pdf/2409.01234.pdf",
                    source="arxiv",
                    source_id="2409.01234",
                    is_preprint=True,
                    is_published=False,
                    is_visible=True,
                ),
                "authors": [
                    (james, "James Chen", 1),
                    (priya, "Priya Sharma", 2),
                ],
                "tags": [theme_ml, tag_methods],
            },
            {
                "publication": Publication(
                    title="Uncertainty-Aware Active Learning for Scientific Discovery",
                    abstract=(
                        "We study uncertainty-aware active learning strategies for "
                        "prioritizing experiments in scientific workflows."
                    ),
                    year=2022,
                    publication_date="2022-07-18",
                    type="article",
                    venue="Nature Machine Intelligence",
                    doi="10.1000/example.2022.004",
                    url="https://doi.org/10.1000/example.2022.004",
                    pdf_url="https://example.edu/papers/uncertainty-active-learning.pdf",
                    source="crossref",
                    source_id="10.1000/example.2022.004",
                    is_preprint=False,
                    is_published=True,
                    is_visible=True,
                ),
                "authors": [
                    (elena, "Dr. Elena Vasquez", 1),
                    (marcus, "Marcus Webb", 2),
                ],
                "tags": [theme_design, theme_ml],
            },
            {
                "publication": Publication(
                    title="Efficient Simulation of Reaction Pathways with Neural Potentials",
                    abstract=(
                        "Preprint on combining neural potentials with enhanced sampling "
                        "for reaction pathway exploration."
                    ),
                    year=2025,
                    publication_date="2025-01-10",
                    type="article",
                    venue="ChemRxiv",
                    doi="10.1000/example.2025.005",
                    url="https://chemrxiv.org/example/2025.005",
                    pdf_url="https://example.edu/preprints/neural-potentials.pdf",
                    source="manual",
                    source_id="chemrxiv-2025-005",
                    is_preprint=True,
                    is_published=False,
                    is_visible=True,
                ),
                "authors": [
                    (priya, "Priya Sharma", 1),
                    (elena, "Dr. Elena Vasquez", 2),
                ],
                "tags": [theme_chem, tag_methods],
            },
            {
                "publication": Publication(
                    title="Interpretable Models for High-Throughput Screening",
                    abstract=(
                        "Conference paper on interpretable machine learning models "
                        "for high-throughput screening campaigns."
                    ),
                    year=2021,
                    publication_date="2021-05-12",
                    type="conference",
                    venue="ICML 2021",
                    doi="10.1000/example.2021.006",
                    url="https://doi.org/10.1000/example.2021.006",
                    pdf_url="https://example.edu/papers/interpretable-hts.pdf",
                    source="openalex",
                    source_id="W9876543210",
                    is_preprint=False,
                    is_published=True,
                    is_visible=True,
                ),
                "authors": [
                    (elena, "Dr. Elena Vasquez", 1),
                    (james, "James Chen", 2),
                    (priya, "Priya Sharma", 3),
                    (marcus, "Marcus Webb", 4),
                ],
                "tags": [theme_design, tag_collab],
            },
            {
                "publication": Publication(
                    title="Draft: Multimodal Fusion for Materials Discovery",
                    abstract=(
                        "Internal draft manuscript exploring multimodal fusion of "
                        "spectroscopy and microscopy data."
                    ),
                    year=2025,
                    publication_date="2025-02-01",
                    type="article",
                    venue="Unpublished manuscript",
                    doi=None,
                    url=None,
                    pdf_url=None,
                    source="manual",
                    source_id="internal-draft-2025",
                    is_preprint=True,
                    is_published=False,
                    is_visible=False,
                ),
                "authors": [
                    (james, "James Chen", 1),
                ],
                "tags": [theme_ml],
            },
        ]

        for item in publications_data:
            publication = item["publication"]
            db.session.add(publication)
            db.session.flush()

            for member, author_name, position in item["authors"]:
                db.session.add(
                    PublicationAuthor(
                        publication_id=publication.id,
                        member_id=member.id,
                        author_name=author_name,
                        author_position=position,
                    )
                )

            for tag in item.get("tags", []):
                db.session.add(
                    PublicationTag(
                        publication_id=publication.id,
                        tag_id=tag.id,
                    )
                )

        db.session.commit()
        print("Database seeded successfully.")
        print(f"  Members: {Member.query.count()}")
        print(f"  Publications: {Publication.query.count()}")
        print(f"  Authorship links: {PublicationAuthor.query.count()}")
        print(f"  Tags & themes: {Tag.query.count()}")


if __name__ == "__main__":
    seed()
