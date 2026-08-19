"""
Inbound webhook — OpenVox pushes a GET request here when an SMS arrives.

OpenVox SMS-to-HTTP config (SMS → SMS Settings → SMS to HTTP):
  Enable: ON
  URL: http://<THIS_MACHINE_IP>:8000/api
       ?from=phonenumber&port=port&channel=portname&text=message
       &time=time&imsi=imsi&status=status&openvox=openvox

Only the port (9501 → 8000) and path (/api) need to change from the
default OpenVox template. All parameter names are kept as OpenVox sends them.

OpenVox parameters used:
  from    — sender phone number
  text    — SMS message body
  port    — GSM port number
  channel — GSM port name (e.g. gsm-1.1)
  time    — timestamp from device
  imsi    — SIM IMSI
  status  — delivery status

Must return HTTP 2xx; OpenVox retries on non-2xx.
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


def _handle_inbound():
    # OpenVox sends: from=<number>, text=<body>, port=<n>, channel=<name>
    from_number = request.args.get("from", "unknown")
    msg         = request.args.get("text", "")
    port        = request.args.get("port", "")
    channel     = request.args.get("channel", "")

    log.info("Inbound SMS: from=%s port=%s channel=%s msg=%r", from_number, port, channel, msg)

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


@bp.get("/api")
def openvox_inbound():
    """Primary endpoint — matches the /api path OpenVox uses by default."""
    return _handle_inbound()


@bp.get("/webhook/inbound")
def inbound():
    """Legacy path kept for compatibility."""
    return _handle_inbound()
