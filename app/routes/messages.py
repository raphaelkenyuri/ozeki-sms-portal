from datetime import datetime

from flask import Blueprint, flash, redirect, request, url_for

from app.database import get_db
from app import ozeki

bp = Blueprint("messages", __name__)


@bp.post("/messages/send")
def send_message():
    raw = request.form.getlist("recipients[]")
    body = request.form.get("body", "").strip()
    group_id = request.form.get("group_id", "").strip()

    # Resolve group members into the recipients list
    if group_id:
        try:
            with get_db() as db:
                with db.cursor() as cur:
                    cur.execute(
                        """
                        SELECT c.phone_number, c.name
                        FROM contacts c
                        JOIN contact_groups cg ON cg.contact_id = c.id
                        WHERE cg.group_id = %s
                        """,
                        (group_id,),
                    )
                    for row in cur.fetchall():
                        raw.append(row["phone_number"])
        except Exception:
            pass  # fall through with whatever recipients[] were submitted

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

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Create campaign record before sending
    campaign_id = None
    try:
        with get_db() as db:
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO campaigns (body, recipient_count, created_at) VALUES (%s, %s, %s)",
                    (body, len(recipients), now),
                )
                campaign_id = cur.lastrowid
    except Exception:
        pass  # campaign tracking failure must not block sending

    sent_ok = []
    sent_fail = []

    for recipient in recipients:
        try:
            result = ozeki.send_message(recipient=recipient, messagedata=body)
        except Exception:
            result = {"result": "error", "messageid": None}

        msg_id_raw = result.get("messageid")
        ozeki_msg_id = None if (not msg_id_raw or msg_id_raw == "null") else msg_id_raw

        with get_db() as db:
            with db.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO outbound_messages
                        (address_ref, body, ozeki_msg_id, status, sent_at, campaign_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (recipient, body, ozeki_msg_id, result.get("result"), now, campaign_id),
                )

        if result.get("result") == "sending":
            sent_ok.append(recipient)
        else:
            sent_fail.append(recipient)

    campaign_label = f" (Campaign #{campaign_id})" if campaign_id else ""

    if sent_fail and not sent_ok:
        flash(f"Failed to send to: {', '.join(sent_fail)}. Check gateway logs.", "error")
    elif sent_fail:
        flash(
            f"Sent to {len(sent_ok)} recipient(s){campaign_label}. Failed for: {', '.join(sent_fail)}.",
            "error",
        )
    else:
        flash(f"Message sent to {len(sent_ok)} recipient(s){campaign_label}.", "success")

    return redirect(url_for("contacts.list_contacts"))
