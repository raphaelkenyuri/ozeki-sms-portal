from datetime import datetime

from flask import Blueprint, flash, redirect, request, url_for

from app.database import get_db
from app import ozeki

bp = Blueprint("messages", __name__)


@bp.post("/messages/send")
def send_message():
    raw = request.form.getlist("recipients[]")
    body = request.form.get("body", "").strip()

    # de-duplicate preserving order, drop blanks
    seen = set()
    recipients = []
    for r in raw:
        r = r.strip()
        if r and r not in seen:
            seen.add(r)
            recipients.append(r)

    if not recipients or not body:
        flash("Add at least one recipient and a message before sending.", "error")
        return redirect(url_for("contacts.list_contacts"))

    sent_ok = []
    sent_fail = []
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    for recipient in recipients:
        try:
            result = ozeki.send_message(recipient=recipient, messagedata=body)
        except Exception:
            result = {"result": "error", "messageid": None}

        with get_db() as db:
            with db.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO outbound_messages (address_ref, body, ozeki_msg_id, status, sent_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (recipient, body, result.get("messageid") or None, result.get("result"), now),
                )

        if result.get("result") == "sending":
            sent_ok.append(recipient)
        else:
            sent_fail.append(recipient)

    if sent_fail and not sent_ok:
        flash(f"Failed to send to: {', '.join(sent_fail)}. Check gateway logs.", "error")
    elif sent_fail:
        flash(
            f"Sent to {len(sent_ok)} recipient(s). Failed for: {', '.join(sent_fail)}.",
            "error",
        )
    else:
        flash(f"Message sent to {len(sent_ok)} recipient(s).", "success")

    return redirect(url_for("contacts.list_contacts"))
