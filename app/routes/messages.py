from datetime import datetime

from flask import Blueprint, flash, redirect, request, url_for

from app.database import get_db
from app import ozeki

bp = Blueprint("messages", __name__)


@bp.post("/messages/send")
def send_message():
    address_ref = request.form.get("address_ref", "").strip()
    body = request.form.get("body", "").strip()

    if not address_ref or not body:
        flash("Please enter a phone number and a message before sending.", "error")
        return redirect(url_for("addresses.list_addresses"))

    result = ozeki.send_message(recipient=address_ref, messagedata=body)

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO outbound_messages (address_ref, body, ozeki_msg_id, status, sent_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    address_ref,
                    body,
                    result.get("messageid") or None,
                    result.get("result"),
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )

    if result.get("result") != "sending":
        flash(f"OpenVox could not send the message to {address_ref}. Check gateway logs.", "error")
        return redirect(url_for("addresses.list_addresses"))

    flash(f"Message sent to {address_ref}.", "success")
    return redirect(url_for("addresses.list_addresses"))
