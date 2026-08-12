"""
Inbound webhook — Ozeki HTTP Client user calls this URL when a message arrives.

Configure the URL template in Ozeki's HTTP Client user settings as:
  http://YOUR_HOST:5000/webhook/inbound?from=$originator&to=$recipient&msg=$messagedata&msgid=$messageid&time=$submitdate

Ozeki substitutes the $variables before making the GET request.
Must return HTTP 2xx; Ozeki retries on non-2xx.
"""

import logging
import re
from datetime import datetime

from flask import Blueprint, request

from app.database import get_db

log = logging.getLogger(__name__)
bp = Blueprint("webhook", __name__)


def _extract_code(text: str):
    m = re.search(r"\d", text or "")
    return int(m.group()) if m else None


@bp.get("/webhook/inbound")
def inbound():
    from_number = request.args.get("from", "unknown")
    msg         = request.args.get("msg", "")
    msgid       = request.args.get("msgid", "")

    log.info("Inbound webhook: from=%s msgid=%s msg=%r", from_number, msgid, msg)

    code = _extract_code(msg)
    translated = None

    if code is not None:
        with get_db() as db:
            with db.cursor() as cur:
                cur.execute("SELECT label FROM response_codes WHERE code = %s", (code,))
                row = cur.fetchone()
                translated = row["label"] if row else None

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO inbound_responses
                    (from_number, raw_message, response_code, translated_status, received_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    from_number,
                    msg,
                    code if translated else None,
                    translated,
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )

    return ("OK", 200)
