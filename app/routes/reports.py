from flask import Blueprint, render_template

from app.database import get_db

bp = Blueprint("reports", __name__)


@bp.get("/reports")
def reports():
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(translated_status, 'Unknown') AS status, COUNT(*) AS total
                FROM inbound_responses
                GROUP BY translated_status
                ORDER BY total DESC
                """
            )
            by_code = cur.fetchall()

            cur.execute(
                """
                SELECT from_number,
                       COALESCE(translated_status, 'Unknown') AS status,
                       COUNT(*) AS total,
                       MAX(received_at) AS last_received
                FROM inbound_responses
                GROUP BY from_number, translated_status
                ORDER BY from_number, status
                """
            )
            by_address = cur.fetchall()

            cur.execute(
                """
                SELECT address_ref, body, ozeki_msg_id, status, sent_at
                FROM outbound_messages
                ORDER BY sent_at DESC
                LIMIT 50
                """
            )
            outbound = cur.fetchall()

    return render_template("report.html", by_code=by_code, by_address=by_address, outbound=outbound)
