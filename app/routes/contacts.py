from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.database import get_db

bp = Blueprint("contacts", __name__)


@bp.get("/contacts")
def list_contacts():
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("SELECT id, name, phone_number, group_tag, notes, created_at FROM contacts ORDER BY name ASC")
            contacts = cur.fetchall()
    return render_template("index.html", contacts=contacts)


@bp.post("/contacts/add")
def add_contact():
    name = request.form.get("name", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    group_tag = request.form.get("group_tag", "").strip() or None

    if not name or not phone_number:
        flash("Name and phone number are required.", "error")
        return redirect(url_for("contacts.list_contacts"))

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contacts (name, phone_number, group_tag)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE name = VALUES(name), group_tag = VALUES(group_tag)
                """,
                (name, phone_number, group_tag),
            )

    flash(f"{name} added to contacts.", "success")
    return redirect(url_for("contacts.list_contacts"))


@bp.post("/contacts/delete/<int:contact_id>")
def delete_contact(contact_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))

    flash("Contact removed.", "success")
    return redirect(url_for("contacts.list_contacts"))
