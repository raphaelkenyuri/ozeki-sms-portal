# OpenVox SMS Gateway Portal

A lightweight Python/Flask web application that integrates with an **OpenVox GSM SMS Gateway**. It acts as a **client and reporting layer** — OpenVox is the source of truth for all SMS activity. Every table in the local MariaDB database is a cache or projection that can be fully rebuilt from OpenVox.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installing MariaDB on Linux](#installing-mariadb-on-linux)
- [WSL Setup](#wsl-setup)
  - [1. Install system packages](#1-install-system-packages)
  - [2. Start and configure MariaDB](#2-start-and-configure-mariadb)
  - [3. Load the schema](#3-load-the-schema)
  - [4. Configure the app](#4-configure-the-app)
  - [5. Run the app](#5-run-the-app)
- [Accessing the App](#accessing-the-app)
- [Deploy from GitHub](#deploy-from-github)
- [Running Database Migrations](#running-database-migrations)
- [Pushing Changes to GitHub](#pushing-changes-to-github)
- [Exposing the Webhook (ngrok)](#exposing-the-webhook-ngrok)
- [Configuring OpenVox](#configuring-openvox)
  - [Outbound send (sendsms)](#outbound-send-sendsms)
  - [Inbound webhook (HTTP to SMS)](#inbound-webhook-http-to-sms)
- [Application Routes](#application-routes)
- [Database Schema](#database-schema)
- [Environment Variables](#environment-variables)
- [OpenVox HTTP API Reference](#openvox-http-api-reference)
- [Response Code Mapping](#response-code-mapping)
- [Contact Book](#contact-book)
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

The typical workflow is:

1. **Send**: Select an address in the UI and send a message. The app calls the OpenVox `/sendsms` HTTP API and stores the returned message ID.
2. **Receive**: Recipients reply with a numeric code (2, 3, or 4). OpenVox forwards the inbound SMS to this app's webhook endpoint via an HTTP GET push.
3. **Report**: The app translates the numeric code to a label (Safe / Unsafe / Out of the country) and stores it. A reporting page shows responses grouped by status and by sender.

```
[ Browser ] ──► [ Flask App :8000 ] ──► [ OpenVox Gateway :80 ]
                        │                         │
                        │◄──── inbound SMS ────────┘  (HTTP GET push)
                        │
                   [ MariaDB ]   (cache only — rebuildable)
```

---

## Architecture

| Principle | Detail |
|---|---|
| **OpenVox is authoritative** | The app never invents state. All data originates from OpenVox. |
| **DB is a cache** | Any table can be dropped and rebuilt from OpenVox. |
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
- **OpenVox GSM Gateway** reachable on the local network (e.g. `192.168.150.20`)
- **(Optional)** [ngrok](https://ngrok.com) to expose the webhook for local testing

---

## Installing MariaDB on Linux

### 1. Install

```bash
sudo apt-get update
sudo apt-get install -y mariadb-server
```

### 2. Start the service

```bash
sudo service mariadb start
```

> **WSL note:** MariaDB does not start automatically on boot in WSL. Run `sudo service mariadb start` each session, or add it to your `~/.bashrc` to automate it.
> On a regular Linux server with systemd, use `sudo systemctl enable --now mariadb` instead so it starts on boot.

### 3. Secure the installation

```bash
sudo mysql_secure_installation
```

This sets a root password and removes the test database.

### 4. Create the app database and user

```bash
sudo mariadb -e "
  CREATE DATABASE IF NOT EXISTS ozeki_app CHARACTER SET utf8mb4;
  CREATE USER IF NOT EXISTS 'ozeki_app'@'localhost' IDENTIFIED BY 'changeme';
  GRANT ALL ON ozeki_app.* TO 'ozeki_app'@'localhost';
"
```

> Change `changeme` to a real password and update `DB_PASSWORD` in `.env` to match.

### 5. Load the schema

```bash
sudo mariadb ozeki_app < schema.sql
```

### 6. Verify

```bash
sudo mariadb ozeki_app -e "SHOW TABLES; SELECT * FROM response_codes;"
```

Expected: 5 tables listed, and rows for codes 2, 3, 4.

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
OPENVOX_BASE_URL=http://192.168.150.20    # your OpenVox gateway IP
OPENVOX_USERNAME=smsuser
OPENVOX_PASSWORD=your_openvox_password

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

The app redirects `/` → `/contacts`, so you land on the contacts and send page immediately.

---

## Deploy from GitHub

Use this approach when you want to run the app on a machine that already has Ozeki deployed — clone the repo, configure `.env` for that environment, and start the app. No file transfer needed.

### 1. Clone the repo

```bash
git clone https://github.com/raphaelkenyuri/ozeki-sms-portal.git
cd ozeki-sms-portal
```

### 2. Install dependencies

```bash
sudo apt-get update
sudo apt-get install -y mariadb-server python3-flask python3-pymysql
```

### 3. Set up MariaDB

```bash
sudo service mariadb start

sudo mariadb -e "
  CREATE DATABASE IF NOT EXISTS ozeki_app CHARACTER SET utf8mb4;
  CREATE USER IF NOT EXISTS 'ozeki_app'@'localhost' IDENTIFIED BY 'changeme';
  GRANT ALL ON ozeki_app.* TO 'ozeki_app'@'localhost';
"

sudo mariadb ozeki_app < schema.sql
```

### 4. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```ini
OPENVOX_BASE_URL=http://192.168.150.20   # OpenVox gateway IP on your LAN
OPENVOX_USERNAME=smsuser
OPENVOX_PASSWORD=your_openvox_password
DB_PASSWORD=changeme                      # must match what you set above
```

> **Ensure OpenVox can reach your webhook URL.** The callback URL you configure on the OpenVox device must resolve to this machine's real LAN IP — not `localhost` or a WSL-only address. Use ngrok if you're testing from WSL.

### 5. Start the app

```bash
python3 -m app.main
```

Or in the background:

```bash
nohup python3 -m app.main > /tmp/ozeki-app.log 2>&1 &
```

### 6. Verify

```bash
curl --noproxy '*' http://localhost:8000/health
# Expected: {"status": "ok"}
```

Then open `http://localhost:8000` in a browser — you should land on the contacts page.

---

## Running Database Migrations

When a new version of the app adds database tables or columns, a numbered migration file is included in the project root (e.g. `migration_001_contacts.sql`). Run each migration once against your existing database — they use `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` so they are safe to re-run.

### Run a migration

```bash
sudo mariadb ozeki_app < ~/ozeki/migration_001_contacts.sql
```

### Verify it applied

```bash
sudo mariadb ozeki_app -e "DESCRIBE contacts;"
```

### Migration history

| File | What it adds |
|---|---|
| `schema.sql` | Full baseline schema — run on a **fresh** database only |
| `migration_001_contacts.sql` | `contacts` table — standalone address book (name, phone, group) |

> **Rule:** Always run migrations in order. Never run `schema.sql` against an existing database that already has data — it only creates tables that don't exist yet, but `schema.sql` is intended for fresh installs. For an existing database, use only the numbered migration files.

---

## Pushing Changes to GitHub

The repository is hosted at `https://github.com/raphaelkenyuri/ozeki-sms-portal`. Use the standard git workflow:

### 1. Check what changed

```bash
cd ~/ozeki
git status        # see modified / untracked files
git diff          # see line-by-line changes
```

### 2. Stage and commit

```bash
# Stage specific files (preferred — avoids accidentally committing .env)
git add app/routes/contacts.py app/templates/index.html app/static/app.css

# Or stage all tracked changes (never commit .env this way)
git add -p        # interactive — review each hunk before staging

# Commit with a clear message
git commit -m "feat: describe what you changed"
```

> **Never commit `.env`** — it contains secrets. It is listed in `.gitignore` but double-check with `git status` before pushing.

### 3. Push

```bash
git push origin main
```

### 4. Pull updates on another machine

```bash
cd ~/ozeki
git pull origin main

# Run any new migration files included in the pull
sudo mariadb ozeki_app < ~/ozeki/migration_001_contacts.sql

# Stop the running app, then restart it to load the new code
pkill -f "app.main"
nohup python3 -m app.main > /tmp/ozeki-app.log 2>&1 &
echo "App restarted. Logs: tail -f /tmp/ozeki-app.log"
```

> **Why restart?** Flask loads all Python files at startup. A `git pull` updates the files on disk but the running process continues to use the old code in memory. You must stop and restart the app for changes to take effect.

> **Check it's running:** `curl --noproxy '*' http://localhost:8000/health` should return `{"status": "ok"}`.

### Commit message conventions

This repo uses [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Use for |
|---|---|
| `feat:` | New feature or capability |
| `fix:` | Bug fix |
| `docs:` | README or comment changes only |
| `refactor:` | Code restructuring with no behaviour change |
| `chore:` | Dependencies, config, tooling |

---

## Exposing the Webhook from WSL

The Flask app runs inside WSL on a private subnet (e.g. `172.20.252.111`). The OpenVox device is on the physical LAN (`192.168.150.x`) and cannot reach WSL directly. You must forward port 8000 from your Windows host into WSL.

### Option A — Windows port forwarding (recommended)

Run in **PowerShell as Administrator** on Windows:

```powershell
# Get current WSL IP
wsl hostname -I

# Forward Windows port 8000 → WSL (replace 172.20.252.111 with your WSL IP)
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=172.20.252.111

# Allow through Windows Firewall
netsh advfirewall firewall add rule name="OpenVox SMS Port 8000" dir=in action=allow protocol=TCP localport=8000
```

Verify it works from another machine on the LAN:
```bash
curl http://192.168.150.246:8000/health
# Expected: {"status":"ok"}
```

> **Note:** The WSL IP changes every time WSL restarts. Re-run `wsl hostname -I` and update the `portproxy` rule after each reboot.

To remove the rule later:
```powershell
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
```

### Option B — ngrok tunnel

```bash
sudo snap install ngrok
ngrok config add-authtoken <your-token>
ngrok http 8000
# Forwarding: https://a1b2c3d4.ngrok.io → http://localhost:8000
```

Use the ngrok URL as the OpenVox callback base (see next section).

---

## Configuring OpenVox

### Outbound send (sendsms)

The app sends messages by calling the OpenVox `/sendsms` HTTP API. Set the credentials in `.env`:

```ini
OPENVOX_BASE_URL=http://192.168.150.20
OPENVOX_USERNAME=smsuser
OPENVOX_PASSWORD=your_password
```

No configuration is needed on the OpenVox device itself for outbound — the app calls it directly.

> **Corporate proxy note:** The app uses `httpx` with `trust_env=False` so the corporate `HTTP_PROXY` does not intercept requests to the OpenVox device on the local network.

### Inbound webhook (SMS to HTTP)

On the OpenVox web UI (`http://192.168.150.20`), go to **SMS → SMS Settings → SMS to HTTP**:

| Setting | Value |
|---|---|
| Enable | ON |
| Enable SMS Reports to HTTP | ON |
| Enable AsyncSMS Result to HTTP | ON |
| URL | see below |

Set the URL to (keep all parameter names exactly as shown — only change the IP and port):

```
http://192.168.150.246:8000/api?from=phonenumber&port=port&channel=portname&text=message&time=time&imsi=imsi&status=status&openvox=openvox
```

Replace `192.168.150.246` with your Windows machine's LAN IP. The path `/api` and all parameter names must stay exactly as shown — the app reads `from` and `text` which are the native OpenVox field names.

**How it works:** When OpenVox receives an SMS it fills in the parameter values and GETs that URL. The app reads `from` (sender) and `text` (message body), parses the response code digit, and stores the result.

**OpenVox parameter mapping:**

| OpenVox param | What it contains |
|---|---|
| `from` | Sender's phone number |
| `text` | SMS message body |
| `port` | GSM port number |
| `channel` | GSM port name (e.g. gsm-1.1) |
| `time` | Timestamp |
| `imsi` | SIM IMSI |
| `status` | Delivery status |

> The endpoint always returns `200 OK`. OpenVox retries on non-2xx.

---

## Application Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Redirects to `/contacts` |
| `GET` | `/health` | Returns `{"status": "ok"}` — for monitoring |
| `GET` | `/contacts` | Contact book + multi-recipient send form |
| `POST` | `/contacts/add` | Add or update a contact (name, phone, group) |
| `POST` | `/contacts/delete/<id>` | Remove a contact by ID |
| `POST` | `/messages/send` | Send to one or more recipients (`recipients[]`); logs each separately |
| `GET` | `/api` | Primary inbound SMS webhook (OpenVox params: `from`, `text`) |
| `GET` | `/webhook/inbound` | Alias for `/api` (legacy path) |
| `GET` | `/reports` | Reporting page: by-code + by-sender breakdowns |
| `GET` | `/reports/export` | Download Excel export of the report |

---

## Database Schema

The database has two categories of tables: **application data** (contacts — managed in the app, source of truth) and **cache/reporting** (messages and responses derived from gateway activity).

### `contacts` _(added in migration_001)_
The standalone address book. Managed entirely within the app — not synced from the gateway.

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `name` | VARCHAR(255) | Display name (required) |
| `phone_number` | VARCHAR(30) UNIQUE | International format, e.g. `+41791234567` (required) |
| `group_tag` | VARCHAR(100) | Optional group label, e.g. `Field Team North` |
| `notes` | VARCHAR(500) | Optional free-text note |
| `created_at` | DATETIME | Set automatically on insert |

---

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
| `address_ref` | VARCHAR(100) | The phone number or address ref it was sent to |
| `body` | TEXT | Message content |
| `ozeki_msg_id` | VARCHAR(16) | Message ID returned by OpenVox (may be `"null"` until device assigns one) |
| `status` | VARCHAR(50) | OpenVox result string (e.g. `sending`) |
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
| `OPENVOX_BASE_URL` | `http://192.168.150.20` | Base URL of your OpenVox gateway |
| `OPENVOX_USERNAME` | `smsuser` | HTTP API username on the OpenVox device |
| `OPENVOX_PASSWORD` | _(empty)_ | HTTP API password on the OpenVox device |
| `DB_HOST` | `127.0.0.1` | MariaDB host |
| `DB_PORT` | `3306` | MariaDB port |
| `DB_USER` | `ozeki_app` | MariaDB username |
| `DB_PASSWORD` | `changeme` | MariaDB password |
| `DB_NAME` | `ozeki_app` | MariaDB database name |
| `APP_PORT` | `8000` | Port the Flask app listens on |

---

## OpenVox HTTP API Reference

### Send a message

```
GET http://<openvox-host>/sendsms
    ?username=<user>
    &password=<pass>
    &phonenumber=<number-or-address>
    &message=<url-encoded-message>
```

**Success response (JSON):**
```json
{
  "message": "Are you safe?",
  "report": [{
    "1": [{
      "port": "1",
      "phonenumber": "254716046448",
      "time": "2026-08-19 14:40:52",
      "id": "null",
      "result": "sending"
    }]
  }]
}
```

`result == "sending"` means the gateway accepted the message. The `id` field is the message correlation key stored in `outbound_messages.ozeki_msg_id` (may be the string `"null"` until the device assigns a real ID).

### Receive (inbound push)

OpenVox does **not** expose a polling inbox API. Instead it pushes inbound SMS to a configured callback URL via HTTP GET. Configure on the device at **SMS → SMS Settings → SMS to HTTP**:

```
http://192.168.150.246:8000/api?from=phonenumber&port=port&channel=portname&text=message&time=time&imsi=imsi&status=status&openvox=openvox
```

OpenVox fills in the values (no `${}` syntax — the field name after `=` is the template variable). The app endpoint is `/api` and reads `from` (sender) and `text` (body).

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

## Contact Book

The app has a built-in address book at `/contacts`. Contacts are managed entirely within the app — they are not synced from the gateway.

### Add a contact

1. Go to `/contacts`
2. Fill in **Name** (required), **Phone number** (required, international format e.g. `+41791234567`), and optionally a **Group** label
3. Click **Add contact** — the contact appears in the list immediately

Adding a contact with the same phone number as an existing one updates the name and group (upsert — no duplicate error).

### Send to multiple recipients

The send form uses a chip-based multi-recipient picker:

- **Type a number** in the recipients field and press **Enter** or **comma** → it becomes a chip
- **Click a contact** in the picker list below the search box → it becomes a chip
- **Remove a chip** by clicking × or pressing Backspace when the field is empty
- Add as many recipients as needed, then compose your message and click **Send**

Each recipient is sent to independently and logged as a separate row in `outbound_messages`.

### Import from Excel _(coming soon)_

The "Import from Excel" button is visible but disabled pending an agreed template. Once the template is finalised, a `/contacts/import` route will process the upload and bulk-insert contacts.

---

## Rebuilding the Database

Since all data is derived from OpenVox, you can wipe and rebuild at any time:

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
│   ├── ozeki.py         # OpenVox HTTP API client (send_message, list_addresses)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── addresses.py # /addresses/* (legacy, kept for backward compat)
│   │   ├── contacts.py  # /contacts, /contacts/add, /contacts/delete/<id>
│   │   ├── messages.py  # /messages/send (multi-recipient loop)
│   │   ├── webhook.py   # /api, /webhook/inbound
│   │   └── reports.py   # /reports, /reports/export
│   └── templates/
│       ├── base.html    # Shared layout, sidebar nav, flash banners
│       ├── index.html   # Contact book + chip-based send form
│       └── report.html  # Response breakdown tables + Excel export
├── Dockerfile               # Container image (python:3.11-slim + pip install)
├── docker-compose.yml       # App + MariaDB 11 services
├── requirements-docker.txt  # Pinned pip deps for Docker image
├── .dockerignore
├── schema.sql               # Full baseline DDL (fresh installs only)
├── migration_001_contacts.sql  # Adds contacts table (run on existing DBs)
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

### OpenVox rejects the message (app returns 502)
- Verify `OPENVOX_BASE_URL`, `OPENVOX_USERNAME`, `OPENVOX_PASSWORD` in `.env`
- Test the OpenVox send endpoint directly from the browser: `http://192.168.150.20/sendsms?username=smsuser&password=<pass>&phonenumber=254716046448&message=test`
- The OpenVox device must be reachable from the machine running the app (not routed through the corporate proxy — this is handled automatically with `trust_env=False`)

### Inbound webhook not firing

1. **Check app logs** — if no request from OpenVox appears, the device can't reach your machine:
   ```bash
   tail -f /tmp/ozeki-app.log
   # Should show: GET /api?from=...&text=... when a reply arrives
   ```
2. **WSL port forwarding** — most common cause in WSL. Run in PowerShell as Administrator:
   ```powershell
   wsl hostname -I   # get WSL IP
   netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=<WSL_IP>
   netsh advfirewall firewall add rule name="OpenVox SMS Port 8000" dir=in action=allow protocol=TCP localport=8000
   ```
3. **Verify from another machine** on the LAN:
   ```bash
   curl http://192.168.150.246:8000/health
   # Must return: {"status":"ok"}
   ```
4. **Test the endpoint manually** (simulates an OpenVox push):
   ```bash
   curl --noproxy '*' "http://localhost:8000/api?from=%2B254702118106&text=2&port=1&channel=gsm-1.1"
   ```
5. **Check OpenVox config** — SMS → SMS Settings → SMS to HTTP must be enabled and the URL must use `/api` path with `from=phonenumber&text=message` params.

### Address sync does nothing
Expected — OpenVox does not expose a REST API for listing addresses. Add addresses manually via the form. See [Address Management](#address-management).
