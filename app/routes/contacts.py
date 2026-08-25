import json

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

            # Build group → members map for JS group picker
            cur.execute(
                """
                SELECT cg.group_id, c.phone_number, c.name
                FROM contact_groups cg
                JOIN contacts c ON c.id = cg.contact_id
                ORDER BY cg.group_id, c.name
                """
            )
            group_members_map = {}
            for row in cur.fetchall():
                gid = str(row["group_id"])
                group_members_map.setdefault(gid, []).append(
                    {"phone": row["phone_number"], "name": row["name"]}
                )

    group_members_json = json.dumps(group_members_map)
    return render_template(
        "index.html",
        contacts=contacts,
        groups=groups,
        group_members_json=group_members_json,
    )


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
            # Use SELECT to get canonical id (lastrowid unreliable on UPSERT)
            cur.execute("SELECT id FROM contacts WHERE phone_number = %s", (phone_number,))
            row = cur.fetchone()
            contact_id = row["id"] if row else None

        if contact_id and group_ids:
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
        elif contact_id and not group_ids:
            # If no groups selected, clear existing membership
            with db.cursor() as cur:
                cur.execute("DELETE FROM contact_groups WHERE contact_id = %s", (contact_id,))

    flash(f"{name} added to contacts.", "success")
    return redirect(url_for("contacts.list_contacts"))


@bp.post("/contacts/delete/<int:contact_id>")
def delete_contact(contact_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))

    flash("Contact removed.", "success")
    return redirect(url_for("contacts.list_contacts"))
