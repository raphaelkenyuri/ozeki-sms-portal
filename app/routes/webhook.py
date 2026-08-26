"""
Inbound webhook — OpenVox pushes a GET request here when an SMS arrives or
when a delivery report is ready.

OpenVox SMS-to-HTTP config (SMS → SMS Settings → SMS to HTTP):
  Enable: ON
  URL: http://<THIS_MACHINE_IP>:8000/api
       ?from=phonenumber&port=port&channel=portname&text=message
       &time=time&imsi=imsi&status=status&openvox=openvox

Delivery reports (Enable AsyncSMS Result to HTTP: ON) arrive at the same
endpoint with different parameters: id=<msg_id>&status=<DELIVERED|FAILED>
and no `from` or `text` fields.

Must return HTTP 2xx; OpenVox retries on non-2xx.

Response keyword matching: full message text (normalized) is looked up in the
response_keywords table. Falls back to the first word if the full message
doesn't match. Examples: "safe", "two", "unsafe", "ooc", "out of country".
"""

import logging
import re
from datetime import datetime

from flask import Blueprint, request

from app.database import get_db

log = logging.getLogger(__name__)
bp = Blueprint("webhook", __name__)


def _lookup_response_code(text: str):
    """Return (code, label) by matching normalized text against response_keywords."""
    if not text:
        return None, None
    normalized = re.sub(r"[^a-z0-9 ]", "", text.strip().lower())
    normalized = re.sub(r" +", " ", normalized).strip()
    if not normalized:
        return None, None

    candidates = [normalized]
    parts = normalized.split()
    if len(parts) > 1:
        candidates.append(parts[0])

    with get_db() as db:
        with db.cursor() as cur:
            for candidate in candidates:
                cur.execute(
                    "SELECT rk.code, rc.label "
                    "FROM response_keywords rk "
                    "JOIN response_codes rc ON rc.code = rk.code "
                    "WHERE rk.keyword = %s",
                    (candidate,),
                )
                row = cur.fetchone()
                if row:
                    return row["code"], row["label"]
    return None, None


def _handle_delivery_report(msg_id: str, status: str):
    """Update outbound_messages.delivery_status when OpenVox confirms delivery."""
    if not msg_id:
        log.warning("Delivery report missing message id — ignored")
        return ("OK", 200)

    log.info("Delivery report: id=%s status=%s", msg_id, status)

    try:
        with get_db() as db:
            with db.cursor() as cur:
                cur.execute(
                    "UPDATE outbound_messages SET delivery_status = %s WHERE ozeki_msg_id = %s",
                    (status, msg_id),
                )
                if cur.rowcount == 0:
                    log.warning("Delivery report for unknown ozeki_msg_id=%s — no row matched", msg_id)
    except Exception as exc:
        log.error("Error saving delivery report: %s", exc)

    return ("OK", 200)


def _handle_inbound_sms():
    """Process an inbound SMS reply and store in inbound_responses."""
    from_number = request.args.get("from", "unknown")
    msg         = request.args.get("text", "")
    port        = request.args.get("port", "")
    channel     = request.args.get("channel", "")

    log.info("Inbound SMS: from=%s port=%s channel=%s msg=%r", from_number, port, channel, msg)

    code, translated = _lookup_response_code(msg)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with get_db() as db:
            with db.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO inbound_responses
                        (from_number, raw_message, response_code, translated_status, received_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (from_number, msg, code, translated, now),
                )
                inbound_id = cur.lastrowid

            # Link to the most recent campaign that sent to this number,
            # respecting each campaign's own response_window_days.
            with db.cursor() as cur:
                cur.execute(
                    """
                    SELECT o.campaign_id
                    FROM outbound_messages o
                    JOIN campaigns c ON c.id = o.campaign_id
                    WHERE o.address_ref = %s
                      AND o.campaign_id IS NOT NULL
                      AND o.sent_at >= CASE c.response_window_unit
                          WHEN 'minutes' THEN DATE_SUB(NOW(), INTERVAL c.response_window_days MINUTE)
                          WHEN 'hours'   THEN DATE_SUB(NOW(), INTERVAL c.response_window_days HOUR)
                          ELSE                DATE_SUB(NOW(), INTERVAL c.response_window_days DAY)
                      END
                    ORDER BY o.sent_at DESC
                    LIMIT 1
                    """,
                    (from_number,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE inbound_responses SET campaign_id = %s WHERE id = %s",
                        (row["campaign_id"], inbound_id),
                    )
    except Exception as exc:
        log.error("Error saving inbound SMS: %s", exc)

    return ("OK", 200)


def _handle_inbound():
    text       = request.args.get("text", "").strip()
    msg_id     = request.args.get("id",   "").strip()
    raw_status = request.args.get("status", "").strip()
    from_num   = request.args.get("from", "").strip()

    is_delivery_report = bool(msg_id and not text and not from_num)

    if is_delivery_report:
        return _handle_delivery_report(msg_id, raw_status)
    return _handle_inbound_sms()


@bp.get("/api")
def openvox_inbound():
    """Primary endpoint — matches the /api path OpenVox uses by default."""
    return _handle_inbound()


@bp.get("/webhook/inbound")
def inbound():
    """Legacy path kept for compatibility."""
    return _handle_inbound()
