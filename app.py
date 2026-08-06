"""Lab Publications Portal - Flask application."""
from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for
from urllib.parse import urlparse

import config
from database.db import init_db
from services import auth_service, export_service, member_service, publication_service, sync_log_service, sync_service, tag_service


def create_app():
    """Application factory."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{config.DATABASE_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    init_db(app)
    register_context_processors(app)
    register_routes(app)
    register_template_filters(app)

    from services.auto_sync_scheduler import init_auto_sync

    init_auto_sync(app)
    return app


def register_context_processors(app):
    """Inject shared template variables."""

    @app.context_processor
    def inject_auth_state():
        return {
            "admin_logged_in": auth_service.is_admin_logged_in(),
            "config": config,
            "lab_name": config.LAB_NAME,
            "lab_website_url": config.LAB_WEBSITE_URL,
            "lab_tagline": config.LAB_TAGLINE,
            "archive_title": config.ARCHIVE_TITLE,
            "archive_tagline": config.ARCHIVE_TAGLINE,
            "university_name": config.UNIVERSITY_NAME,
            "university_url": config.UNIVERSITY_URL,
            "site_name": config.SITE_NAME,
            "site_description": config.SITE_DESCRIPTION,
        }


def register_template_filters(app):
    """Register Jinja template filters."""

    @app.template_filter("groupby_year")
    def groupby_year_filter(publications):
        return publication_service.group_publications_by_year(publications)


def _publication_filters_from_request(include_hidden=False, preprints_only=False):
    """Parse publication filter query parameters."""
    return {
        "year": request.args.get("year") or None,
        "pub_type": request.args.get("type") or None,
        "member_id": request.args.get("member") or None,
        "preprint_status": request.args.get("preprint_status") or None,
        "search": request.args.get("search") or None,
        "tag_id": request.args.get("tag") or None,
        "theme_id": request.args.get("theme") or None,
        "preprints_only": preprints_only,
        "include_hidden": include_hidden,
    }


def _filtered_publications(include_hidden=False, preprints_only=False):
    """Return publications matching current request filters."""
    return publication_service.filter_publications(
        **_publication_filters_from_request(
            include_hidden=include_hidden,
            preprints_only=preprints_only,
        )
    )


def _download_response(content, filename, mimetype):
    """Return a file download response."""
    return Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def register_routes(app):
    """Register all application routes."""

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            total_publications=publication_service.count_publications(),
            total_preprints=publication_service.count_publications(preprints_only=True),
            total_members=member_service.count_members(),
            recent_publications=publication_service.get_recent_publications(limit=5),
        )

    @app.route("/members")
    def members():
        return render_template(
            "members.html",
            members=member_service.get_all_members(),
        )

    @app.route("/join", methods=["GET", "POST"])
    def member_register():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name is required.", "danger")
            else:
                try:
                    member = member_service.submit_member_registration(
                        request.form,
                        photo_file=_photo_from_request(),
                    )
                except ValueError as exc:
                    flash(str(exc), "danger")
                else:
                    return render_template(
                        "member_register_success.html",
                        member=member,
                    )
        return render_template("member_register.html")

    @app.route("/members/<int:member_id>")
    def member_detail(member_id):
        member = member_service.get_public_member(member_id)
        if not member:
            abort(404)
        publications = publication_service.get_publications_for_member(member_id)
        grouped = publication_service.split_publications_by_status(publications)
        profile = member_service.get_member_profile_summary(member_id)
        return render_template(
            "member_detail.html",
            member=member,
            grouped_published=grouped["published"],
            grouped_preprints=grouped["preprints"],
            profile=profile,
        )

    @app.route("/publications")
    def publications():
        filters = {
            "year": request.args.get("year", ""),
            "type": request.args.get("type", ""),
            "member": request.args.get("member", ""),
            "preprint_status": request.args.get("preprint_status", ""),
            "search": request.args.get("search", ""),
            "tag": request.args.get("tag", ""),
            "theme": request.args.get("theme", ""),
        }
        results = publication_service.filter_publications(
            year=filters["year"] or None,
            pub_type=filters["type"] or None,
            member_id=filters["member"] or None,
            preprint_status=filters["preprint_status"] or None,
            search=filters["search"] or None,
            tag_id=filters["tag"] or None,
            theme_id=filters["theme"] or None,
        )
        options = publication_service.get_filter_options()
        return render_template(
            "publications.html",
            publications=results,
            filters=filters,
            filter_options=options,
        )

    @app.route("/publications/export.csv")
    def export_publications_csv():
        publications = _filtered_publications()
        content = export_service.publications_to_csv(publications)
        return _download_response(content, "publications.csv", "text/csv; charset=utf-8")

    @app.route("/publications/export.bib")
    def export_publications_bib():
        publications = _filtered_publications()
        content = export_service.publications_to_bibtex(publications)
        return _download_response(content, "publications.bib", "application/x-bibtex; charset=utf-8")

    @app.route("/preprints/export.csv")
    def export_preprints_csv():
        publications = _filtered_publications(preprints_only=True)
        content = export_service.publications_to_csv(publications)
        return _download_response(content, "preprints.csv", "text/csv; charset=utf-8")

    @app.route("/preprints/export.bib")
    def export_preprints_bib():
        publications = _filtered_publications(preprints_only=True)
        content = export_service.publications_to_bibtex(publications)
        return _download_response(content, "preprints.bib", "application/x-bibtex; charset=utf-8")

    @app.route("/members/<int:member_id>/export.csv")
    def export_member_publications_csv(member_id):
        member = member_service.get_public_member(member_id)
        if not member:
            abort(404)
        publications = publication_service.get_publications_for_member(member_id)
        content = export_service.publications_to_csv(publications)
        filename = f"{member.name.replace(' ', '_').lower()}_publications.csv"
        return _download_response(content, filename, "text/csv; charset=utf-8")

    @app.route("/members/<int:member_id>/export.bib")
    def export_member_publications_bib(member_id):
        member = member_service.get_public_member(member_id)
        if not member:
            abort(404)
        publications = publication_service.get_publications_for_member(member_id)
        content = export_service.publications_to_bibtex(publications)
        filename = f"{member.name.replace(' ', '_').lower()}_publications.bib"
        return _download_response(content, filename, "application/x-bibtex; charset=utf-8")

    @app.route("/preprints")
    def preprints():
        results = publication_service.filter_publications(preprints_only=True)
        return render_template("preprints.html", publications=results)

    @app.route("/publications/<int:publication_id>")
    def publication_detail(publication_id):
        publication = publication_service.get_publication_by_id(publication_id)
        if not publication:
            abort(404)
        return render_template("publication_detail.html", publication=publication)

    @app.route("/themes")
    def themes():
        return render_template(
            "themes.html",
            themes=tag_service.get_themes_with_counts(),
        )

    @app.route("/themes/<slug>")
    def theme_detail(slug):
        theme = tag_service.get_tag_by_slug(slug)
        if not theme or theme.kind != "theme":
            abort(404)
        publications = publication_service.filter_publications(theme_id=theme.id)
        return render_template(
            "theme_detail.html",
            theme=theme,
            publications=publications,
        )

    # --- Admin routes (password protected) ---

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if auth_service.is_admin_logged_in():
            return redirect(url_for("admin_home"))

        if request.method == "POST":
            password = request.form.get("password", "")
            if auth_service.verify_password(password):
                auth_service.login_admin()
                flash("Logged in successfully.", "success")
                next_url = request.args.get("next")
                if next_url and _is_safe_redirect(next_url):
                    return redirect(next_url)
                return redirect(url_for("admin_home"))
            flash("Incorrect password.", "danger")

        return render_template("admin_login.html")

    @app.route("/admin/logout")
    def admin_logout():
        auth_service.logout_admin()
        flash("Logged out successfully.", "success")
        return redirect(url_for("index"))

    @app.route("/admin")
    @auth_service.admin_required
    def admin_home():
        return render_template(
            "admin.html",
            member_count=member_service.count_members(include_inactive=True),
            pending_member_count=member_service.count_pending_members(),
            publication_count=publication_service.count_publications(),
            preprint_count=publication_service.count_publications(preprints_only=True),
        )

    @app.route("/admin/members")
    @auth_service.admin_required
    def admin_members():
        return render_template(
            "admin_members.html",
            members=member_service.get_all_members_admin(),
            pending_members=member_service.get_pending_members(),
        )

    @app.route("/admin/members/new", methods=["GET", "POST"])
    @auth_service.admin_required
    def admin_member_new():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name is required.", "danger")
            else:
                try:
                    member = member_service.create_member_admin(
                        request.form,
                        photo_file=_photo_from_request(),
                    )
                except ValueError as exc:
                    flash(str(exc), "danger")
                    return render_template("admin_member_form.html", member=None)
                sync_result = sync_service.sync_member_publications(member.id)
                flash(
                    f"Member created. {sync_service.format_member_sync_message(member.name, sync_result, sync_result.get('sources'))}",
                    "success" if sync_result.get("status") != "error" else "danger",
                )
                return redirect(url_for("admin_member_edit", member_id=member.id))
        return render_template("admin_member_form.html", member=None)

    @app.route("/admin/members/<int:member_id>/edit", methods=["GET", "POST"])
    @auth_service.admin_required
    def admin_member_edit(member_id):
        member = member_service.get_member_by_id(member_id)
        if not member:
            abort(404)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name is required.", "danger")
            else:
                try:
                    member_service.update_member(
                        member,
                        request.form,
                        photo_file=_photo_from_request(),
                    )
                except ValueError as exc:
                    flash(str(exc), "danger")
                    return render_template("admin_member_form.html", member=member)
                sync_result = sync_service.sync_member_publications(member.id)
                flash(
                    f"Member updated. {sync_service.format_member_sync_message(member.name, sync_result, sync_result.get('sources'))}",
                    "success" if sync_result.get("status") != "error" else "danger",
                )
                return redirect(url_for("admin_member_edit", member_id=member.id))

        return render_template("admin_member_form.html", member=member)

    @app.route("/admin/members/<int:member_id>/sync", methods=["POST"])
    @auth_service.admin_required
    def admin_member_sync(member_id):
        member = member_service.get_member_by_id(member_id)
        if not member:
            abort(404)
        sync_result = sync_service.sync_member_publications(member.id)
        flash(
            sync_service.format_member_sync_message(
                member.name, sync_result, sync_result.get("sources")
            ),
            "success" if sync_result.get("status") != "error" else "danger",
        )
        return redirect(url_for("admin_member_edit", member_id=member.id))

    @app.route("/admin/members/<int:member_id>/approve", methods=["POST"])
    @auth_service.admin_required
    def admin_member_approve(member_id):
        member = member_service.get_member_by_id(member_id)
        if not member:
            abort(404)
        if member.approval_status != member_service.APPROVAL_PENDING:
            flash("Only pending profiles can be approved.", "danger")
            return redirect(url_for("admin_member_edit", member_id=member.id))

        member_service.approve_member(member)
        sync_result = sync_service.sync_member_publications(member.id)
        flash(
            f"Approved {member.name}. {sync_service.format_member_sync_message(member.name, sync_result, sync_result.get('sources'))}",
            "success" if sync_result.get("status") != "error" else "danger",
        )
        return redirect(url_for("admin_member_edit", member_id=member.id))

    @app.route("/admin/members/<int:member_id>/reject", methods=["POST"])
    @auth_service.admin_required
    def admin_member_reject(member_id):
        member = member_service.get_member_by_id(member_id)
        if not member:
            abort(404)
        if member.approval_status != member_service.APPROVAL_PENDING:
            flash("Only pending profiles can be rejected.", "danger")
            return redirect(url_for("admin_member_edit", member_id=member.id))

        member_service.reject_member(member)
        flash(f"Rejected profile for {member.name}.", "success")
        return redirect(url_for("admin_members"))

    @app.route("/admin/members/<int:member_id>/delete", methods=["GET", "POST"])
    @auth_service.admin_required
    def admin_member_delete(member_id):
        member = member_service.get_member_by_id(member_id)
        if not member:
            abort(404)

        publications = member_service.get_linked_publications(member_id)

        if request.method == "POST":
            result = member_service.delete_member_with_publications(member_id)
            if not result:
                abort(404)
            flash(
                (
                    f"Deleted {result['member_name']} and "
                    f"{result['publications_deleted']} linked publication(s)."
                ),
                "success",
            )
            return redirect(url_for("admin_members"))

        return render_template(
            "admin_member_delete.html",
            member=member,
            publications=publications,
            publication_count=len(publications),
        )

    @app.route("/admin/publications")
    @auth_service.admin_required
    def admin_publications():
        return render_template(
            "admin_publications.html",
            publications=publication_service.get_all_publications_admin(),
        )

    @app.route("/admin/publications/export.csv")
    @auth_service.admin_required
    def admin_export_publications_csv():
        publications = publication_service.get_all_publications_admin()
        content = export_service.publications_to_csv(publications, include_admin_fields=True)
        return _download_response(content, "all_publications.csv", "text/csv; charset=utf-8")

    @app.route("/admin/publications/export.bib")
    @auth_service.admin_required
    def admin_export_publications_bib():
        publications = publication_service.get_all_publications_admin()
        content = export_service.publications_to_bibtex(publications)
        return _download_response(content, "all_publications.bib", "application/x-bibtex; charset=utf-8")

    @app.route("/admin/publications/new", methods=["GET", "POST"])
    @auth_service.admin_required
    def admin_publication_new():
        members = member_service.get_all_members_admin()
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            if not title:
                flash("Title is required.", "danger")
            else:
                authors_data = publication_service.parse_authors_from_form(request.form)
                tag_ids = tag_service.parse_tag_ids_from_form(request.form)
                publication_service.create_publication(request.form, authors_data, tag_ids=tag_ids)
                flash("Publication created successfully.", "success")
                return redirect(url_for("admin_publications"))

        return render_template(
            "admin_publication_form.html",
            publication=None,
            members=members,
            all_tags=tag_service.get_all_tags(kind="tag"),
            all_themes=tag_service.get_all_tags(kind="theme"),
        )

    @app.route("/admin/publications/<int:publication_id>/edit", methods=["GET", "POST"])
    @auth_service.admin_required
    def admin_publication_edit(publication_id):
        publication = publication_service.get_publication_by_id_admin(publication_id)
        if not publication:
            abort(404)

        members = member_service.get_all_members_admin()

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            if not title:
                flash("Title is required.", "danger")
            else:
                authors_data = publication_service.parse_authors_from_form(request.form)
                tag_ids = tag_service.parse_tag_ids_from_form(request.form)
                publication_service.update_publication(
                    publication, request.form, authors_data, tag_ids=tag_ids
                )
                flash("Publication updated successfully.", "success")
                return redirect(url_for("admin_publications"))

        return render_template(
            "admin_publication_form.html",
            publication=publication,
            members=members,
            all_tags=tag_service.get_all_tags(kind="tag"),
            all_themes=tag_service.get_all_tags(kind="theme"),
        )

    @app.route("/admin/tags")
    @auth_service.admin_required
    def admin_tags():
        return render_template(
            "admin_tags.html",
            tags=tag_service.get_all_tags(kind="tag"),
            themes=tag_service.get_all_tags(kind="theme"),
        )

    @app.route("/admin/tags/new", methods=["GET", "POST"])
    @auth_service.admin_required
    def admin_tag_new():
        kind = request.args.get("kind", "tag")
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name is required.", "danger")
            else:
                tag_service.create_tag(request.form)
                flash("Tag created successfully.", "success")
                return redirect(url_for("admin_tags"))
        return render_template("admin_tag_form.html", tag=None, kind=kind)

    @app.route("/admin/tags/<int:tag_id>/edit", methods=["GET", "POST"])
    @auth_service.admin_required
    def admin_tag_edit(tag_id):
        tag = tag_service.get_tag_by_id(tag_id)
        if not tag:
            abort(404)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name is required.", "danger")
            else:
                tag_service.update_tag(tag, request.form)
                flash("Tag updated successfully.", "success")
                return redirect(url_for("admin_tags"))

        return render_template("admin_tag_form.html", tag=tag, kind=tag.kind)

    @app.route("/admin/tags/<int:tag_id>/delete", methods=["POST"])
    @auth_service.admin_required
    def admin_tag_delete(tag_id):
        result = tag_service.delete_tag(tag_id)
        if not result:
            abort(404)
        flash(f"Deleted tag '{result['name']}'.", "success")
        return redirect(url_for("admin_tags"))

    @app.route("/admin/publications/<int:publication_id>/toggle-visibility", methods=["POST"])
    @auth_service.admin_required
    def admin_publication_toggle_visibility(publication_id):
        publication = publication_service.get_publication_by_id_admin(publication_id)
        if not publication:
            abort(404)
        publication_service.toggle_visibility(publication)
        state = "visible" if publication.is_visible else "hidden"
        flash(f"Publication marked as {state}.", "success")
        return redirect(url_for("admin_publications"))

    @app.route("/admin/sync", methods=["GET", "POST"])
    @auth_service.admin_required
    def admin_sync():
        members = member_service.get_all_members_admin()

        if request.method == "POST":
            action = request.form.get("action", "")
            result = None

            if action == "orcid":
                member_id = request.form.get("member_id", type=int)
                result = sync_service.sync_from_orcid(member_id)
            elif action == "openalex":
                member_id = request.form.get("member_id", type=int)
                result = sync_service.sync_from_openalex(member_id)
            elif action == "crossref":
                result = sync_service.sync_from_crossref(request.form.get("doi", ""))
            elif action == "arxiv":
                member_id = request.form.get("member_id", type=int)
                result = sync_service.sync_from_arxiv(
                    request.form.get("query", ""),
                    member_id=member_id,
                )
            elif action == "sync_all":
                active_only = request.form.get("active_only") == "1"
                result = sync_service.sync_all_members(active_only=active_only)
            else:
                flash("Unknown sync action.", "danger")

            if result:
                status = result.get("status", "error")
                category = "success" if status in {"success", "partial", "skipped"} else "danger"
                flash(result.get("message", "Sync finished."), category)
                return redirect(url_for("admin_sync"))

        return render_template(
            "admin_sync.html",
            members=members,
            logs=sync_log_service.get_recent_logs(),
        )


def _photo_from_request():
    """Return the uploaded profile photo from the current request, if any."""
    return request.files.get("photo")


def _is_safe_redirect(target):
    """Allow redirects only to local paths."""
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(target)
    return (
        redirect_url.scheme in ("", host_url.scheme)
        and redirect_url.netloc in ("", host_url.netloc)
        and redirect_url.path.startswith("/")
    )


app = create_app()


if __name__ == "__main__":
    app.run(debug=config.DEBUG, port=config.PORT)
