"""
Ozeki HTTP API client.

Confirmed API:
  Send:  GET /api?action=sendmessage&username=U&password=P
                 &recipient=R&messagetype=SMS:TEXT&messagedata=M
         Response XML: <statuscode>, <statusmessage>, <messageid>, <recipient>

  Poll:  GET /api?action=receivemessage&username=U&password=P
                 &folder=inbox&limit=N&afterdownload=delete
         Response XML per <message>: messageid, originator, recipient,
                 messagetype, messagedata, senttime, receivedtime

Address listing: no confirmed REST endpoint — list_addresses() is a stub.
"""

import logging
from typing import Optional

import httpx
from lxml import etree

from app import config

log = logging.getLogger(__name__)

_AUTH = {"username": config.OZEKI_USERNAME, "password": config.OZEKI_PASSWORD}


def _base() -> str:
    return config.OZEKI_BASE_URL.rstrip("/")


def _parse_xml(text: str) -> etree._Element:
    return etree.fromstring(text.encode())


def send_message(recipient: str, messagedata: str, originator: Optional[str] = None) -> dict:
    params = {
        **_AUTH,
        "action": "sendmessage",
        "recipient": recipient,
        "messagetype": "SMS:TEXT",
        "messagedata": messagedata,
        "responseformat": "xml",
    }
    if originator:
        params["originator"] = originator

    resp = httpx.get(f"{_base()}/api", params=params, timeout=15)
    resp.raise_for_status()
    root = _parse_xml(resp.text)

    def _text(tag: str) -> str:
        el = root.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    return {
        "statuscode": _text("statuscode"),
        "statusmessage": _text("statusmessage"),
        "messageid": _text("messageid"),
        "recipient": _text("recipient"),
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
