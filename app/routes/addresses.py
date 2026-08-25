from datetime import datetime

from flask import Blueprint, redirect, render_template, request, jsonify, url_for

from app.database import get_db
from app import ozeki

bp = Blueprint("addresses", __name__)


@bp.get("/addresses")
def list_addresses():
    with get_db() as db:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM addresses_cache ORDER BY name")
            addresses = cur.fetchall()
    return render_template("index.html", addresses=addresses)


@bp.post("/addresses/sync")
def sync_addresses():
    from_ozeki = ozeki.list_addresses()  # stub -  returns []

    with get_db() as db:
        with db.cursor() as cur:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            for addr in from_ozeki:
                cur.execute(
                    """
                    INSERT INTO addresses_cache (ozeki_ref, name, last_synced)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE name = VALUES(name), last_synced = VALUES(last_synced)
                    """,
                    (addr["ozeki_ref"], addr.get("name"), now),
                )
            cur.execute("SELECT * FROM addresses_cache ORDER BY name")
            addresses = cur.fetchall()

    return jsonify({
        "synced_from_ozeki": len(from_ozeki),
        "total_cached": len(addresses),
        "addresses": addresses,
        "note": "Ozeki address API not yet confirmed. Seed manually via the Add form.",
    })


@bp.post("/addresses/add")
def add_address():
    ozeki_ref = request.form.get("ozeki_ref", "").strip()
    name = request.form.get("name", "").strip()
    if not ozeki_ref:
        return "ozeki_ref is required", 400

    with get_db() as db:
        with db.cursor() as cur:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                """
                INSERT INTO addresses_cache (ozeki_ref, name, last_synced)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE name = VALUES(name), last_synced = VALUES(last_synced)
                """,
                (ozeki_ref, name or ozeki_ref, now),
            )

    return redirect(url_for("addresses.list_addresses"))
