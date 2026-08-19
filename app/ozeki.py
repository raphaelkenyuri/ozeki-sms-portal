"""
OpenVox SMS Gateway HTTP API client.

Send:
  GET /sendsms?username=U&password=P&phonenumber=N&message=M
  Response JSON: {"message":"...", "report":[{"1":[{"port":"1",
      "phonenumber":"...","time":"...","id":"null","result":"sending"}]}]}
  Success: report[0]["1"][0]["result"] == "sending"

Receive (inbound):
  OpenVox pushes GET requests to the configured callback URL when an SMS
  arrives.  Configure on the device at SMS → SMS Settings → HTTP to SMS:
    http://YOUR_HOST:8000/webhook/inbound?phonenumber=${phonenumber}&message=${message}&id=${id}&port=${port}&time=${time}

Address listing: no confirmed REST endpoint — list_addresses() is a stub.
"""

import logging
from typing import Optional

import httpx
from lxml import etree

from app import config

log = logging.getLogger(__name__)


def send_message(recipient: str, messagedata: str, originator: Optional[str] = None) -> dict:
    params = {
        "username":    config.OPENVOX_USERNAME,
        "password":    config.OPENVOX_PASSWORD,
        "phonenumber": recipient,
        "message":     messagedata,
    }
    # trust_env=False prevents the corporate HTTP_PROXY from intercepting
    # requests to the OpenVox device on the local network.
    with httpx.Client(trust_env=False) as client:
        resp = client.get(
            f"{config.OPENVOX_BASE_URL.rstrip('/')}/sendsms",
            params=params,
            timeout=15,
        )
    resp.raise_for_status()
    data = resp.json()
    try:
        entry = data["report"][0]["1"][0]
    except (KeyError, IndexError, TypeError):
        log.error("Unexpected OpenVox response: %s", data)
        return {"result": "error", "messageid": None, "raw": data}
    return {
        "result":    entry.get("result", ""),
        "messageid": entry.get("id"),
        "port":      entry.get("port", ""),
    }


def poll_inbox(limit: int = 100, afterdownload: str = "delete") -> list:
    params = {
        **_AUTH,
        "action": "receivemessage",
        "folder": "inbox",
        "limit": limit,
        "afterdownload": afterdownload,
        "responseformat": "xml",
    }

    resp = httpx.get(f"{_base()}/api", params=params, timeout=15)
    resp.raise_for_status()
    root = _parse_xml(resp.text)

    messages = []
    for msg in root.findall(".//message"):
        def _t(tag: str, _msg=msg) -> str:
            el = _msg.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        messages.append({
            "messageid":    _t("messageid"),
            "originator":   _t("originator"),
            "recipient":    _t("recipient"),
            "messagetype":  _t("messagetype"),
            "messagedata":  _t("messagedata"),
            "senttime":     _t("senttime"),
            "receivedtime": _t("receivedtime"),
        })

    return messages


def list_addresses() -> list:
    # TODO v2: implement once Ozeki address REST API endpoint is confirmed.
    # No clean API found in the official docs at planning time.
    log.warning(
        "list_addresses() is a stub — no confirmed Ozeki address API. "
        "Seed addresses manually via the Add form."
    )
    return []
