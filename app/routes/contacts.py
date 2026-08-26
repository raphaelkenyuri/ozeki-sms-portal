from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.database import get_db

bp = Blueprint("contacts", __name__)


@bp.get("/contacts")
def list_contacts():
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.name, c.phone_number, c.group_tag,
                       c.site, c.department, c.email, c.line_manager,
                       c.notes, c.created_at,
                       GROUP_CONCAT(g.name ORDER BY g.name SEPARATOR ', ') AS group_names
                FROM contacts c
                LEFT JOIN contact_groups cg ON cg.contact_id = c.id
                LEFT JOIN `groups` g ON g.id = cg.group_id
                GROUP BY c.id
                ORDER BY c.name ASC
                """
            )
            contacts = cur.fetchall()

            cur.execute("SELECT id, name FROM `groups` ORDER BY name ASC")
            groups = cur.fetchall()

    return render_template("contacts.html", contacts=contacts, groups=groups)


@bp.post("/contacts/add")
def add_contact():
    name         = request.form.get("name", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    group_tag    = request.form.get("group_tag", "").strip() or None
    site         = request.form.get("site", "").strip() or None
    department   = request.form.get("department", "").strip() or None
    email        = request.form.get("email", "").strip() or None
    line_manager = request.form.get("line_manager", "").strip() or None
    group_ids    = request.form.getlist("group_ids[]")

    if not name or not phone_number:
        flash("Name and phone number are required.", "error")
        return redirect(url_for("contacts.list_contacts"))

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contacts (name, phone_number, group_tag, site, department, email, line_manager)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name         = VALUES(name),
                    group_tag    = VALUES(group_tag),
                    site         = VALUES(site),
                    department   = VALUES(department),
                    email        = VALUES(email),
                    line_manager = VALUES(line_manager)
                """,
                (name, phone_number, group_tag, site, department, email, line_manager),
            )
            cur.execute("SELECT id FROM contacts WHERE phone_number = %s", (phone_number,))
            row = cur.fetchone()
            contact_id = row["id"] if row else None

        if contact_id:
            with db.cursor() as cur:
                cur.execute("DELETE FROM contact_groups WHERE contact_id = %s", (contact_id,))
                for gid in group_ids:
                    try:
                        cur.execute(
                            "INSERT IGNORE INTO contact_groups (contact_id, group_id) VALUES (%s, %s)",
                            (contact_id, int(gid)),
                        )
                    except (ValueError, Exception):
                        pass

            # Always enroll in "All staff" regardless of group selection
            with db.cursor() as cur:
                cur.execute("SELECT id FROM `groups` WHERE name = 'All staff' LIMIT 1")
                all_staff = cur.fetchone()
                if all_staff:
                    cur.execute(
                        "INSERT IGNORE INTO contact_groups (contact_id, group_id) VALUES (%s, %s)",
                        (contact_id, all_staff["id"]),
                    )

    flash(f"{name} added to contacts.", "success")
    return redirect(url_for("contacts.list_contacts"))


@bp.get("/contacts/<int:contact_id>/edit")
def edit_contact(contact_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, name, phone_number, site, department, email, line_manager "
                "FROM contacts WHERE id = %s",
                (contact_id,),
            )
            contact = cur.fetchone()
    if not contact:
        flash("Contact not found.", "error")
        return redirect(url_for("contacts.list_contacts"))
    return render_template("contact_edit.html", contact=contact)


@bp.post("/contacts/<int:contact_id>/edit")
def update_contact(contact_id):
    name         = request.form.get("name", "").strip()
    site         = request.form.get("site", "").strip() or None
    department   = request.form.get("department", "").strip() or None
    email        = request.form.get("email", "").strip() or None
    line_manager = request.form.get("line_manager", "").strip() or None

    if not name:
        flash("Name is required.", "error")
        return redirect(url_for("contacts.edit_contact", contact_id=contact_id))

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE contacts SET name=%s, site=%s, department=%s, email=%s, line_manager=%s "
                "WHERE id=%s",
                (name, site, department, email, line_manager, contact_id),
            )

    flash("Contact updated.", "success")
    return redirect(url_for("contacts.list_contacts"))


@bp.post("/contacts/delete/<int:contact_id>")
def delete_contact(contact_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
    flash("Contact removed.", "success")
    return redirect(url_for("contacts.list_contacts"))
