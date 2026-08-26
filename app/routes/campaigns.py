import json
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import ozeki
from app.database import get_db

bp = Blueprint("campaigns", __name__)


@bp.get("/campaigns")
def list_campaigns():
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.name, c.body, c.created_at, c.recipient_count,
                       COUNT(DISTINCT o.id) AS sent_count,
                       SUM(CASE WHEN o.delivery_status = 'DELIVERED' THEN 1 ELSE 0 END) AS delivered_count,
                       COUNT(DISTINCT ir.from_number) AS responded_count
                FROM campaigns c
                LEFT JOIN outbound_messages o  ON o.campaign_id = c.id
                LEFT JOIN inbound_responses ir ON ir.campaign_id = c.id
                GROUP BY c.id
                ORDER BY c.created_at DESC
                """
            )
            campaigns = cur.fetchall()
    return render_template("campaigns.html", campaigns=campaigns)


@bp.get("/campaigns/new")
def new_campaign():
    return render_template("campaign_new.html")


@bp.post("/campaigns/new")
def create_campaign():
    name = request.form.get("name", "").strip() or None
    body = request.form.get("body", "").strip()
    try:
        window = int(request.form.get("response_window_days", 30))
        window = max(1, min(365, window))
    except (ValueError, TypeError):
        window = 30

    if not body:
        flash("Message body is required.", "error")
        return redirect(url_for("campaigns.new_campaign"))

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO campaigns (name, body, recipient_count, created_at, response_window_days) "
                "VALUES (%s, %s, 0, %s, %s)",
                (name, body, now, window),
            )
            campaign_id = cur.lastrowid

    return redirect(url_for("campaigns.campaign_detail", campaign_id=campaign_id))


@bp.get("/campaigns/<int:campaign_id>")
def campaign_detail(campaign_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, name, body, created_at, recipient_count, response_window_days "
                "FROM campaigns WHERE id = %s",
                (campaign_id,),
            )
            campaign = cur.fetchone()
            if not campaign:
                flash("Campaign not found.", "error")
                return redirect(url_for("campaigns.list_campaigns"))

            cur.execute(
                "SELECT COUNT(*) AS c FROM outbound_messages WHERE campaign_id = %s",
                (campaign_id,),
            )
            has_sent = (cur.fetchone() or {}).get("c", 0) > 0

            cur.execute(
                """
                SELECT address_ref, ozeki_msg_id, status, delivery_status, sent_at
                FROM outbound_messages WHERE campaign_id = %s ORDER BY sent_at ASC
                """,
                (campaign_id,),
            )
            outbound = cur.fetchall()

            cur.execute(
                """
                SELECT ir.from_number,
                       COALESCE(ir.translated_status, 'Unknown') AS status,
                       ir.raw_message, ir.received_at
                FROM inbound_responses ir
                WHERE ir.campaign_id = %s
                  AND ir.received_at = (
                      SELECT MAX(ir2.received_at) FROM inbound_responses ir2
                      WHERE ir2.campaign_id = ir.campaign_id AND ir2.from_number = ir.from_number
                  )
                ORDER BY ir.from_number
                """,
                (campaign_id,),
            )
            responses = cur.fetchall()

            cur.execute(
                """
                SELECT COUNT(DISTINCT o.id) AS sent_count,
                       SUM(CASE WHEN o.delivery_status = 'DELIVERED' THEN 1 ELSE 0 END) AS delivered_count,
                       COUNT(DISTINCT ir.from_number) AS responded_count
                FROM outbound_messages o
                LEFT JOIN inbound_responses ir ON ir.campaign_id = o.campaign_id
                WHERE o.campaign_id = %s
                """,
                (campaign_id,),
            )
            stats = cur.fetchone() or {}

            # Groups with member_count for the send form picker
            cur.execute(
                """
                SELECT g.id, g.name, COUNT(cg.contact_id) AS member_count
                FROM `groups` g
                LEFT JOIN contact_groups cg ON cg.group_id = g.id
                GROUP BY g.id ORDER BY g.name ASC
                """
            )
            groups = cur.fetchall()

            # Contacts for the contact quick-pick
            cur.execute(
                """
                SELECT c.id, c.name, c.phone_number,
                       GROUP_CONCAT(g.name ORDER BY g.name SEPARATOR ', ') AS group_names
                FROM contacts c
                LEFT JOIN contact_groups cg ON cg.contact_id = c.id
                LEFT JOIN `groups` g ON g.id = cg.group_id
                GROUP BY c.id ORDER BY c.name ASC
                """
            )
            contacts = cur.fetchall()

            # Group → members map for JS group picker
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

    return render_template(
        "campaign_detail.html",
        campaign=campaign,
        has_sent=has_sent,
        outbound=outbound,
        responses=responses,
        stats=stats,
        groups=groups,
        contacts=contacts,
        group_members_json=json.dumps(group_members_map),
    )


@bp.post("/campaigns/<int:campaign_id>/send")
def send_campaign(campaign_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("SELECT id, body FROM campaigns WHERE id = %s", (campaign_id,))
            campaign = cur.fetchone()
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("campaigns.list_campaigns"))

    raw = request.form.getlist("recipients[]")
    group_id = request.form.get("group_id", "").strip()

    if group_id:
        try:
            with get_db() as db:
                with db.cursor() as cur:
                    cur.execute(
                        """
                        SELECT c.phone_number FROM contacts c
                        JOIN contact_groups cg ON cg.contact_id = c.id
                        WHERE cg.group_id = %s
                        """,
                        (group_id,),
                    )
                    for row in cur.fetchall():
                        raw.append(row["phone_number"])
        except Exception:
            pass

    seen = set()
    recipients = []
    for r in raw:
        r = r.strip()
        if r and r not in seen:
            seen.add(r)
            recipients.append(r)

    if not recipients:
        flash("Add at least one recipient before sending.", "error")
        return redirect(url_for("campaigns.campaign_detail", campaign_id=campaign_id))

    body = campaign["body"]
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
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

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE campaigns SET recipient_count = recipient_count + %s WHERE id = %s",
                (len(recipients), campaign_id),
            )

    if sent_fail and not sent_ok:
        flash(f"Failed to send to: {', '.join(sent_fail)}. Check gateway logs.", "error")
    elif sent_fail:
        flash(
            f"Sent to {len(sent_ok)} recipient(s). Failed for: {', '.join(sent_fail)}.",
            "error",
        )
    else:
        flash(f"Message sent to {len(sent_ok)} recipient(s).", "success")

    return redirect(url_for("campaigns.campaign_detail", campaign_id=campaign_id))


@bp.post("/campaigns/<int:campaign_id>/edit")
def edit_campaign(campaign_id):
    name = request.form.get("name", "").strip() or None
    try:
        window = int(request.form.get("response_window_days", 30))
        window = max(1, min(365, window))
    except (ValueError, TypeError):
        window = 30

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c FROM outbound_messages WHERE campaign_id = %s",
                (campaign_id,),
            )
            has_sent = (cur.fetchone() or {}).get("c", 0) > 0

            if has_sent:
                cur.execute(
                    "UPDATE campaigns SET name=%s, response_window_days=%s WHERE id=%s",
                    (name, window, campaign_id),
                )
            else:
                body = request.form.get("body", "").strip()
                if not body:
                    flash("Message body is required.", "error")
                    return redirect(url_for("campaigns.campaign_detail", campaign_id=campaign_id))
                cur.execute(
                    "UPDATE campaigns SET name=%s, body=%s, response_window_days=%s WHERE id=%s",
                    (name, body, window, campaign_id),
                )

    flash("Campaign updated.", "success")
    return redirect(url_for("campaigns.campaign_detail", campaign_id=campaign_id))


@bp.post("/campaigns/<int:campaign_id>/delete")
def delete_campaign(campaign_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("DELETE FROM campaigns WHERE id = %s", (campaign_id,))
    flash("Campaign deleted.", "success")
    return redirect(url_for("campaigns.list_campaigns"))
