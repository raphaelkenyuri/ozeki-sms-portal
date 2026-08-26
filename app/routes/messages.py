from datetime import datetime

from flask import Blueprint, flash, redirect, request, url_for

from app.database import get_db
from app import ozeki

bp = Blueprint("messages", __name__)


@bp.post("/messages/send")
def send_message():
    # Sending now happens inside a campaign. Redirect anyone hitting this old URL.
    flash("Please create or open a campaign to send messages.", "error")
    return redirect(url_for("campaigns.new_campaign"))
