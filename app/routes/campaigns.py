from flask import Blueprint, flash, redirect, render_template, url_for

from app.database import get_db

bp = Blueprint("campaigns", __name__)


@bp.get("/campaigns")
def list_campaigns():
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.body, c.created_at, c.recipient_count,
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


@bp.get("/campaigns/<int:campaign_id>")
def campaign_detail(campaign_id):
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                "SELECT id, body, created_at, recipient_count FROM campaigns WHERE id = %s",
                (campaign_id,),
            )
            campaign = cur.fetchone()
            if not campaign:
                flash("Campaign not found.", "error")
                return redirect(url_for("campaigns.list_campaigns"))

            # Outbound: who was sent to and what delivery status
            cur.execute(
                """
                SELECT address_ref, ozeki_msg_id, status, delivery_status, sent_at
                FROM outbound_messages
                WHERE campaign_id = %s
                ORDER BY sent_at ASC
                """,
                (campaign_id,),
            )
            outbound = cur.fetchall()

            # Inbound: deduplicated -  latest response per sender
            cur.execute(
                """
                SELECT ir.from_number,
                       COALESCE(ir.translated_status, 'Unknown') AS status,
                       ir.raw_message,
                       ir.received_at
                FROM inbound_responses ir
                WHERE ir.campaign_id = %s
                  AND ir.received_at = (
                      SELECT MAX(ir2.received_at)
                      FROM inbound_responses ir2
                      WHERE ir2.campaign_id = ir.campaign_id
                        AND ir2.from_number  = ir.from_number
                  )
                ORDER BY ir.from_number
                """,
                (campaign_id,),
            )
            responses = cur.fetchall()

            # Summary counts
            cur.execute(
                """
                SELECT
                    COUNT(DISTINCT o.id) AS sent_count,
                    SUM(CASE WHEN o.delivery_status = 'DELIVERED' THEN 1 ELSE 0 END) AS delivered_count,
                    COUNT(DISTINCT ir.from_number) AS responded_count
                FROM outbound_messages o
                LEFT JOIN inbound_responses ir
                    ON ir.campaign_id = o.campaign_id
                WHERE o.campaign_id = %s
                """,
                (campaign_id,),
            )
            stats = cur.fetchone() or {}

    return render_template(
        "campaign_detail.html",
        campaign=campaign,
        outbound=outbound,
        responses=responses,
        stats=stats,
    )
