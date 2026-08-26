from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.database import get_db

bp = Blueprint("groups", __name__)


@bp.get("/groups")
def list_groups():
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT g.id, g.name, g.description, g.created_at,
                       COUNT(cg.contact_id) AS member_count
                FROM `groups` g
                LEFT JOIN contact_groups cg ON cg.group_id = g.id
                GROUP BY g.id
                ORDER BY g.name ASC
                """
            )
            groups = cur.fetchall()
    return render_template("groups.html", groups=groups)


@bp.post("/groups/add")
def add_group():
    name        = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None

    if not name:
        flash("Group name is required.", "error")
        return redirect(url_for("groups.list_groups"))

    try:
        with get_db() as db:
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO `groups` (name, description) VALUES (%s, %s)",
                    (name, description),
                )
        flash(f"Group '{name}' created.", "success")
    except Exception:
        flash(f"A group named '{name}' already exists.", "error")

    return redirect(url_for("groups.list_groups"))


@bp.get("/groups/<int:group_id>")
def group_detail(group_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("SELECT id, name, description FROM `groups` WHERE id = %s", (group_id,))
            group = cur.fetchone()
            if not group:
                flash("Group not found.", "error")
                return redirect(url_for("groups.list_groups"))

            cur.execute(
                """
                SELECT c.id, c.name, c.phone_number, c.site, c.department
                FROM contacts c
                JOIN contact_groups cg ON cg.contact_id = c.id
                WHERE cg.group_id = %s
                ORDER BY c.name ASC
                """,
                (group_id,),
            )
            members = cur.fetchall()

            # Contacts not in this group (for add-member form)
            cur.execute(
                """
                SELECT c.id, c.name, c.phone_number
                FROM contacts c
                WHERE c.id NOT IN (
                    SELECT contact_id FROM contact_groups WHERE group_id = %s
                )
                ORDER BY c.name ASC
                """,
                (group_id,),
            )
            non_members = cur.fetchall()

    return render_template(
        "group_detail.html",
        group=group,
        members=members,
        non_members=non_members,
    )


@bp.post("/groups/<int:group_id>/edit")
def edit_group(group_id):
    name        = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip() or None

    if not name:
        flash("Group name is required.", "error")
        return redirect(url_for("groups.group_detail", group_id=group_id))

    try:
        with get_db() as db:
            with db.cursor() as cur:
                cur.execute(
                    "UPDATE `groups` SET name=%s, description=%s WHERE id=%s",
                    (name, description, group_id),
                )
        flash("Group updated.", "success")
    except Exception:
        flash("A group with that name already exists.", "error")

    return redirect(url_for("groups.group_detail", group_id=group_id))


@bp.post("/groups/<int:group_id>/add-members")
def add_members(group_id):
    contact_ids = request.form.getlist("contact_ids[]")
    if not contact_ids:
        flash("Select at least one contact.", "error")
        return redirect(url_for("groups.group_detail", group_id=group_id))

    added = 0
    with get_db() as db:
        with db.cursor() as cur:
            for cid in contact_ids:
                try:
                    cur.execute(
                        "INSERT IGNORE INTO contact_groups (contact_id, group_id) VALUES (%s, %s)",
                        (int(cid), group_id),
                    )
                    added += cur.rowcount
                except (ValueError, Exception):
                    pass

    flash(f"{added} contact(s) added to group.", "success")
    return redirect(url_for("groups.group_detail", group_id=group_id))


@bp.post("/groups/<int:group_id>/remove-member")
def remove_member(group_id):
    contact_id = request.form.get("contact_id")
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "DELETE FROM contact_groups WHERE group_id = %s AND contact_id = %s",
                (group_id, contact_id),
            )
    flash("Member removed.", "success")
    return redirect(url_for("groups.group_detail", group_id=group_id))


@bp.post("/groups/<int:group_id>/delete")
def delete_group(group_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("SELECT name FROM `groups` WHERE id = %s", (group_id,))
            row = cur.fetchone()
            name = row["name"] if row else "Group"
            cur.execute("DELETE FROM `groups` WHERE id = %s", (group_id,))
    flash(f"Group '{name}' deleted.", "success")
    return redirect(url_for("groups.list_groups"))
