# Ozeki SMS Gateway MVP

A lightweight Python/Flask web application that integrates with an [Ozeki SMS Gateway](https://ozeki-sms-gateway.com). It acts as a **client and reporting layer** — Ozeki is the source of truth for all SMS activity. Every table in the local MariaDB database is a cache or projection that can be fully rebuilt by re-syncing from Ozeki.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [WSL Setup](#wsl-setup)
  - [1. Install system packages](#1-install-system-packages)
  - [2. Start and configure MariaDB](#2-start-and-configure-mariadb)
  - [3. Load the schema](#3-load-the-schema)
  - [4. Configure the app](#4-configure-the-app)
  - [5. Run the app](#5-run-the-app)
- [Accessing the App](#accessing-the-app)
- [Exposing the Webhook (ngrok)](#exposing-the-webhook-ngrok)
- [Configuring Ozeki](#configuring-ozeki)
  - [HTTP API User (outbound send)](#http-api-user-outbound-send)
  - [HTTP Client User (inbound webhook)](#http-client-user-inbound-webhook)
- [Application Routes](#application-routes)
- [Database Schema](#database-schema)
- [Environment Variables](#environment-variables)
- [Ozeki HTTP API Reference](#ozeki-http-api-reference)
- [Response Code Mapping](#response-code-mapping)
- [Address Management](#address-management)
- [Rebuilding the Database](#rebuilding-the-database)
- [Docker Deployment](#docker-deployment)
  - [Files](#files)
  - [Deploy on a target machine](#deploy-on-a-target-machine)
  - [start.sh Docker commands](#startsh-docker-commands)
  - [Build behind a proxy](#build-behind-a-proxy)
  - [Ship a pre-built image](#ship-a-pre-built-image)
  - [Network note for WSL builds](#network-note-for-wsl-builds)
- [Project Layout](#project-layout)
- [Troubleshooting](#troubleshooting)

---

## Overview

This MVP was built for testing Ozeki SMS Gateway integration. The typical workflow is:

1. **Send**: Select an Ozeki address (recipient group) in the UI and send a message. The app calls Ozeki's HTTP send API and stores the returned message ID.
2. **Receive**: Recipients reply with a numeric code (2, 3, or 4). Ozeki forwards the inbound SMS to this app's webhook endpoint.
3. **Report**: The app translates the numeric code to a label (Safe / Unsafe / Out of the country) and stores it. A reporting page shows responses grouped by status and by sender.

```
[ Browser ] ──► [ Flask App :8000 ] ──► [ Ozeki Gateway ]
                        │                       │
                        │◄──── inbound SMS ─────┘ (webhook push)
                        │
                   [ MariaDB ]   (cache only — rebuildable)
```

---

## Architecture

| Principle | Detail |
|---|---|
| **Ozeki is authoritative** | The app never invents state. All data originates from Ozeki. |
| **DB is a cache** | Any table can be dropped and rebuilt from Ozeki. |
| **No hardcoded secrets** | All credentials and URLs come from `.env`. |
| **Minimal dependencies** | Flask, pymysql, httpx, lxml, Jinja2 — all installable via apt. |

---

## Features

| Feature | Route |
|---|---|
| View cached address list | `GET /addresses` |
| Manually add an address to cache | `POST /addresses/add` |
| Attempt address sync from Ozeki | `POST /addresses/sync` |
| Send a message via Ozeki | `POST /messages/send` |
| Receive inbound replies (webhook) | `GET /webhook/inbound` |
| Report: responses by status code | `GET /reports` |
| Report: responses by sender number | `GET /reports` |
| Report: recent outbound messages | `GET /reports` |
| Health check | `GET /health` |

---

## Prerequisites

- **WSL** (Ubuntu 22.04 recommended) or any Linux environment
- **Python 3.10+** (comes with Ubuntu 22.04)
- **MariaDB** (installed via apt below)
- **Ozeki SMS Gateway** running on a reachable host
- **(Optional)** [ngrok](https://ngrok.com) to expose the webhook for local testing

---

## WSL Setup

### 1. Install system packages

```bash
sudo apt-get update
sudo apt-get install -y mariadb-server python3-flask python3-pymysql
```

> The following packages are already present on a standard Ubuntu 22.04 install and require no extra installation: `python3-httpx` (as `httpx`), `python3-lxml`, `python3-jinja2`.
> If any are missing: `sudo apt-get install -y python3-httpx python3-lxml python3-jinja2`

### 2. Start and configure MariaDB

```bash
sudo service mariadb start

sudo mariadb -e "
  CREATE DATABASE IF NOT EXISTS ozeki_app CHARACTER SET utf8mb4;
  CREATE USER IF NOT EXISTS 'ozeki_app'@'localhost' IDENTIFIED BY 'changeme';
  GRANT ALL ON ozeki_app.* TO 'ozeki_app'@'localhost';
"
```

> Change `changeme` to a stronger password and update `DB_PASSWORD` in `.env` accordingly.

### 3. Load the schema

```bash
sudo mariadb ozeki_app < /home/<you>/ozeki/schema.sql
```

Verify it worked:

```bash
sudo mariadb ozeki_app -e "SHOW TABLES; SELECT * FROM response_codes;"
```

Expected output: 5 tables, and rows for codes 2, 3, 4.

### 4. Configure the app

```bash
cd ~/ozeki
cp .env.example .env
```

Open `.env` and fill in the values for your environment:

```ini
OZEKI_BASE_URL=http://192.168.1.10:9508   # your Ozeki server IP + port
OZEKI_USERNAME=admin
OZEKI_PASSWORD=your_ozeki_password
OZEKI_WEBHOOK_URL=http://YOUR_HOST:8000/webhook/inbound

DB_PASSWORD=changeme   # must match what you set above
```

See [Environment Variables](#environment-variables) for all options.

### 5. Run the app

```bash
cd ~/ozeki
python3 -m app.main
```

Or in the background (persists after closing the terminal):

```bash
nohup python3 -m app.main > /tmp/ozeki-app.log 2>&1 &
echo "PID: $!"
```

To stop it:

```bash
pkill -f "app.main"
```

---

## Accessing the App

Open your browser to:

```
http://localhost:8000
```

> **Corporate proxy note (ICRC/managed laptops):** If `http_proxy` is set in your environment, curl and some tools will route local requests through the proxy and fail. Use `--noproxy '*'` with curl, or just open the URL directly in a browser (browsers typically bypass the proxy for localhost automatically).

The app redirects `/` → `/addresses`, so you land on the address list immediately.

---

## Exposing the Webhook (ngrok)

Ozeki needs to reach your app's `/webhook/inbound` endpoint over the network. In WSL, you need a tunnel.

**Install ngrok** (if not already):

```bash
# Download from https://ngrok.com/download, or:
sudo snap install ngrok
ngrok config add-authtoken <your-token>
```

**Start the tunnel:**

```bash
ngrok http 8000
```

ngrok will print something like:

```
Forwarding  https://a1b2c3d4.ngrok.io -> http://localhost:8000
```

**Update your `.env`:**

```ini
OZEKI_WEBHOOK_URL=https://a1b2c3d4.ngrok.io/webhook/inbound
```

Then use the full webhook URL when configuring Ozeki (see next section).

---

## Configuring Ozeki

### HTTP API User (outbound send)

This app calls Ozeki's HTTP API to send messages. You need an **HTTP API user** in Ozeki with:

- A username and password (set in `.env` as `OZEKI_USERNAME` / `OZEKI_PASSWORD`)
- Permission to send messages

No special webhook URL is needed for this user — it's used in outbound direction only.

### HTTP Client User (inbound webhook)

To receive inbound SMS, create an **HTTP Client user** in Ozeki's admin panel and set its URL template to:

```
http://YOUR_HOST:8000/webhook/inbound?from=$originator&to=$recipient&msg=$messagedata&msgid=$messageid&time=$submitdate
```

Replace `YOUR_HOST:8000` with your ngrok URL (or your server's real host) if Ozeki runs on a different machine.

**How it works:** When Ozeki receives an SMS, it substitutes the `$variables` with the actual message fields and makes a GET request to your URL. The app receives the parameters, parses the numeric response code from the message body, looks it up in the `response_codes` table, and stores the result.

**Ozeki URL template variables used:**

| Variable | Field | Parameter name in our URL |
|---|---|---|
| `$originator` | Sender's phone number | `from` |
| `$recipient` | Recipient (your number) | `to` |
| `$messagedata` | Message body | `msg` |
| `$messageid` | Ozeki's message ID | `msgid` |
| `$submitdate` | Submission timestamp | `time` |

> The webhook must return HTTP 2xx. Ozeki will retry on any other status code. Our endpoint always returns `200 OK`.

---

## Application Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Redirects to `/addresses` |
| `GET` | `/health` | Returns `{"status": "ok"}` — for monitoring |
| `GET` | `/addresses` | Address list page (from DB cache) + send form |
| `POST` | `/addresses/add` | Manually add an address to the local cache |
| `POST` | `/addresses/sync` | Attempt to pull addresses from Ozeki (stub — see [Address Management](#address-management)) |
| `POST` | `/messages/send` | Send a message via Ozeki; stores `ozeki_msg_id` |
| `GET` | `/webhook/inbound` | Inbound SMS webhook called by Ozeki |
| `GET` | `/reports` | Reporting page: by-code + by-sender breakdowns |

---

## Database Schema

All tables are **cache/reporting only**. Ozeki is the source of truth. Any table can be dropped and rebuilt.

### `response_codes`
Lookup table for translating numeric SMS replies to human-readable labels.

| Column | Type | Notes |
|---|---|---|
| `code` | INT PK | The digit the user sends (e.g. `2`) |
| `label` | VARCHAR(50) | Human label (e.g. `Safe`) |

Seeded with: `2 → Safe`, `3 → Unsafe`, `4 → Out of the country`

To add more codes: `INSERT INTO response_codes VALUES (5, 'Your label');`

### `addresses_cache`
Cache of Ozeki address book entries (recipient groups).

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `ozeki_ref` | VARCHAR(100) UNIQUE | Address name as Ozeki knows it — used as `recipient` in send API |
| `name` | VARCHAR(255) | Display name |
| `last_synced` | DATETIME | When this row was last updated |

### `address_members`
Members (phone numbers) belonging to each address. Populated manually or via a future sync.

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `address_ozeki_ref` | VARCHAR(100) | FK → `addresses_cache.ozeki_ref` |
| `phone_number` | VARCHAR(30) | |
| `name` | VARCHAR(255) | |

### `outbound_messages`
Record of every message sent through the app.

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `address_ref` | VARCHAR(100) | The `ozeki_ref` (or phone number) it was sent to |
| `body` | TEXT | Message content |
| `ozeki_msg_id` | VARCHAR(16) | Correlation key returned by Ozeki (e.g. `ERFAV23D`) |
| `status` | VARCHAR(50) | Ozeki's status message |
| `sent_at` | DATETIME | |

### `inbound_responses`
Every inbound message received via the webhook.

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `from_number` | VARCHAR(30) | Sender's phone number |
| `raw_message` | TEXT | Raw message body as received |
| `response_code` | INT | Parsed digit (FK → `response_codes.code`); NULL if unparseable |
| `translated_status` | VARCHAR(50) | Label from `response_codes`; NULL if code unknown |
| `received_at` | DATETIME | |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values. Never commit `.env`.

| Variable | Default | Description |
|---|---|---|
| `OZEKI_BASE_URL` | `http://127.0.0.1:9508` | Base URL of your Ozeki server |
| `OZEKI_USERNAME` | `admin` | HTTP API user username in Ozeki |
| `OZEKI_PASSWORD` | _(empty)_ | HTTP API user password in Ozeki |
| `OZEKI_WEBHOOK_URL` | `http://localhost:8000/webhook/inbound` | Public URL Ozeki calls for inbound messages. Use your ngrok URL when testing. |
| `DB_HOST` | `127.0.0.1` | MariaDB host |
| `DB_PORT` | `3306` | MariaDB port |
| `DB_USER` | `ozeki_app` | MariaDB username |
| `DB_PASSWORD` | `changeme` | MariaDB password |
| `DB_NAME` | `ozeki_app` | MariaDB database name |
| `APP_PORT` | `8000` | Port the Flask app listens on |

---

## Ozeki HTTP API Reference

This app uses two Ozeki HTTP API actions. Both support GET and POST; we use GET.

### Send a message

```
GET http://<ozeki-host>:9508/api
    ?action=sendmessage
    &username=<user>
    &password=<pass>
    &recipient=<address-or-phone>
    &messagetype=SMS:TEXT
    &messagedata=<url-encoded-message>
    &responseformat=xml
```

**Success response (XML):**
```xml
<response>
  <statuscode>0</statuscode>
  <statusmessage>Message accepted for delivery</statusmessage>
  <messageid>ERFAV23D</messageid>
  <recipient>+36201234567</recipient>
</response>
```

`statuscode=0` means accepted. Any other value is an error. `messageid` (max 16 chars) is the correlation key stored in `outbound_messages.ozeki_msg_id`.

### Poll the inbox

```
GET http://<ozeki-host>:9508/api
    ?action=receivemessage
    &username=<user>
    &password=<pass>
    &folder=inbox
    &limit=100
    &afterdownload=delete
    &responseformat=xml
```

**Response (XML):**
```xml
<response>
  <message>
    <messageid>...</messageid>
    <originator>+36201234567</originator>
    <recipient>+36301234567</recipient>
    <messagetype>SMS:TEXT</messagetype>
    <messagedata>Hello</messagedata>
    <senttime>2025-08-10 10:00:00</senttime>
    <receivedtime>2025-08-10 10:00:01</receivedtime>
  </message>
</response>
```

`afterdownload=delete` removes messages from the Ozeki inbox after retrieval. Use `mark` or `untouch` if you want to keep them in Ozeki.

---

## Response Code Mapping

Recipients reply to the sent message with a single digit. The app extracts the first digit from the message body and maps it:

| SMS digit | Meaning |
|---|---|
| `2` | Safe |
| `3` | Unsafe |
| `4` | Out of the country |

The mapping lives in the `response_codes` table — edit it directly to add or change codes without touching the application code.

If a message contains no digit, `response_code` and `translated_status` are stored as NULL. The raw message body is always preserved in `raw_message`.

---

## Address Management

**Ozeki does not expose a confirmed REST API for listing or managing addresses.** The "Sync from Ozeki" button is a stub — it logs a warning and returns an empty list.

### Current workflow (manual)

1. Go to `/addresses`
2. Use the **Add address** form to enter an address
3. Set **Ozeki ref** to the exact address name as it appears in Ozeki (this is what gets passed as `recipient` in the send API)
4. Optionally set a display name

### Sending to a phone number directly

The send form also accepts a raw phone number in international format (e.g. `+41791234567`). Type it in the "Or type a phone number directly" field — it overrides the address dropdown.

### Sending to a group

If Ozeki's address names map to groups/lists (expanding to multiple recipients), pass the group name as `recipient`. Whether Ozeki expands it depends on your Ozeki version and connection type — **verify with a live test** on your instance.

### v2: Implement address sync

When/if Ozeki exposes an address API, implement it in `app/ozeki.py` in the `list_addresses()` function. The rest of the sync path is already wired up.

---

## Rebuilding the Database

Since all data is derived from Ozeki, you can wipe and rebuild at any time:

```bash
sudo mariadb -e "DROP DATABASE ozeki_app; CREATE DATABASE ozeki_app CHARACTER SET utf8mb4;"
sudo mariadb ozeki_app < ~/ozeki/schema.sql
```

Inbound responses will repopulate as new messages arrive via the webhook. Outbound history is lost but can be reconstructed from Ozeki's sent folder if needed.

---

## Docker Deployment

The app ships with a `Dockerfile` and `docker-compose.yml` that run the Flask app and a MariaDB container together. The image is built with `pip install` and requires outbound internet access during the build step (normal on any non-restricted machine).

### Files

| File | Purpose |
|---|---|
| `Dockerfile` | `python:3.11-slim` base + pip install; exposes port 8000 |
| `docker-compose.yml` | Defines `app` + `db` (MariaDB 11) services; auto-runs `schema.sql` on first start |
| `requirements-docker.txt` | Pinned pip dependencies used inside the image |
| `.dockerignore` | Excludes `.env`, `.venv`, `__pycache__` from the build context |
| `package.sh` | Bundles the whole project into `ozeki-sms-app.tar.gz` for transfer |

### Deploy on a target machine

**Step 1 — package the app (run on this machine):**

```bash
cd ~/ozeki
bash package.sh
# Creates ~/ozeki-sms-app.tar.gz
```

**Step 2 — transfer to the target:**

```bash
scp ~/ozeki-sms-app.tar.gz user@target-machine:~
```

**Step 3 — extract, configure, and start (run on target):**

```bash
tar -xzf ozeki-sms-app.tar.gz
cd ozeki
cp .env.example .env
# Edit .env: set OZEKI_BASE_URL, OZEKI_USERNAME, OZEKI_PASSWORD, DB_PASSWORD
bash start.sh docker
```

The first run builds the image, pulls MariaDB 11, loads `schema.sql`, and starts both containers. Subsequent starts reuse the cached image.

> **DB data is persisted** in a Docker named volume (`db_data`). It survives `docker compose down` and is only removed with `docker compose down -v`.

### start.sh Docker commands

`start.sh` wraps the most common Docker operations:

```bash
bash start.sh docker        # build image + start containers (detached)
bash start.sh docker-logs   # follow app container logs (Ctrl+C to exit)
bash start.sh docker-stop   # stop and remove containers (data volume preserved)
```

Raw docker compose equivalents:

```bash
docker compose up --build -d    # start
docker compose logs -f app      # logs
docker compose down             # stop
docker compose ps               # status
docker compose down -v          # stop + wipe DB volume
```

### Build behind a proxy

If the target machine uses an HTTP proxy, pass it as build args:

```bash
docker build \
  --build-arg HTTP_PROXY=http://proxy.example.com:8080 \
  --build-arg HTTPS_PROXY=http://proxy.example.com:8080 \
  -t ozeki-sms-app:latest .
```

Or set them in `docker-compose.yml` under `build.args`:

```yaml
services:
  app:
    build:
      context: .
      args:
        HTTP_PROXY: http://proxy.example.com:8080
        HTTPS_PROXY: http://proxy.example.com:8080
```

### Ship a pre-built image

If you already have a machine where the image built successfully, you can export and import the image directly — no build step needed on the target:

```bash
# On the build machine — save image to file
docker save ozeki-sms-app:latest | gzip > ozeki-sms-app-image.tar.gz

# Transfer
scp ozeki-sms-app-image.tar.gz user@target-machine:~

# On the target — load image, then start (skips build)
docker load < ozeki-sms-app-image.tar.gz
docker compose up -d
```

### Network note for WSL builds

Docker containers on a corporate WSL instance may have no outbound internet access even if the host machine does (the host proxy is not inherited by containers). Symptoms:

- `pip install` fails with `Network is unreachable`
- `apt-get update` fails with connection timeouts

**Workarounds:**
1. **Build on a different machine** (recommended) — use `package.sh` + `scp` as above.
2. **Configure Docker daemon proxy** — create `/etc/docker/daemon.json` with proxy settings and restart Docker:

```json
{
  "proxies": {
    "http-proxy": "http://fgtproxy.gva.icrc.priv:8080",
    "https-proxy": "http://fgtproxy.gva.icrc.priv:8080",
    "no-proxy": "localhost,127.0.0.1"
  }
}
```

```bash
sudo systemctl restart docker
```

---

## Project Layout

```
ozeki/
├── app/
│   ├── __init__.py
│   ├── main.py          # Flask app factory, blueprint registration, entry point
│   ├── config.py        # Reads .env into module-level constants
│   ├── database.py      # pymysql connection context manager (get_db)
│   ├── ozeki.py         # Ozeki HTTP API client (send_message, poll_inbox, list_addresses)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── addresses.py # /addresses, /addresses/add, /addresses/sync
│   │   ├── messages.py  # /messages/send
│   │   ├── webhook.py   # /webhook/inbound
│   │   └── reports.py   # /reports
│   └── templates/
│       ├── base.html    # Shared layout, nav, CSS
│       ├── index.html   # Address list + send form
│       └── report.html  # Response breakdown tables
├── Dockerfile               # Container image (python:3.11-slim + pip install)
├── docker-compose.yml       # App + MariaDB 11 services
├── requirements-docker.txt  # Pinned pip deps for Docker image
├── .dockerignore
├── schema.sql               # MariaDB DDL + seed data
├── start.sh                 # Native and Docker start/stop helper
├── package.sh               # Bundles project into ozeki-sms-app.tar.gz
├── .env.example             # Environment variable template
├── requirements.txt         # Dependency notes (apt-based install)
└── README.md
```

---

## Troubleshooting

### App won't start — `No module named 'flask'`
```bash
sudo apt-get install -y python3-flask python3-pymysql
```

### DB connection error on startup
- Confirm MariaDB is running: `sudo service mariadb start`
- Check credentials in `.env` match what you set in MariaDB
- Test manually: `mariadb -u ozeki_app -p ozeki_app -e "SHOW TABLES;"`

### `curl localhost:8000` returns empty or hangs
A corporate HTTP proxy (`http_proxy` env var) may be intercepting local requests. Bypass it:
```bash
curl --noproxy '*' http://localhost:8000/health
```
Browsers typically bypass the proxy for `localhost` automatically.

### Ozeki rejects the message (`statuscode` ≠ 0)
- Verify `OZEKI_BASE_URL`, `OZEKI_USERNAME`, `OZEKI_PASSWORD` in `.env`
- Check the Ozeki admin panel for the HTTP API user's permissions
- Confirm the `recipient` value matches an address or number Ozeki can reach

### Inbound webhook not firing
- Confirm Ozeki's HTTP Client user URL template is set correctly
- The URL must be reachable from Ozeki's host — use ngrok if testing from WSL
- Check `/tmp/ozeki-app.log` for incoming request logs
- Test manually: `curl --noproxy '*' "http://localhost:8000/webhook/inbound?from=%2B41791234567&msg=2&msgid=test"`

### Address sync does nothing
Expected — the Ozeki address REST API is not yet confirmed. Add addresses manually via the form. See [Address Management](#address-management).
