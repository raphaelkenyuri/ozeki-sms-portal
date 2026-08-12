import logging

from flask import Flask, redirect, url_for

from app.routes import addresses, messages, webhook, reports
from app import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

app = Flask(__name__, template_folder="templates")
app.secret_key = "ozeki-mvp-secret"

app.register_blueprint(addresses.bp)
app.register_blueprint(messages.bp)
app.register_blueprint(webhook.bp)
app.register_blueprint(reports.bp)


@app.get("/")
def root():
    return redirect(url_for("addresses.list_addresses"))


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.APP_PORT, debug=False, use_reloader=False)
