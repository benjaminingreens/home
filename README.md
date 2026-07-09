# HOME

HOME is a local-first personal operating system built entirely around plain
text. Notes, tasks, events, and everything else exist as ordinary
human-readable `.txt` files — the web interface is just one way of viewing
and editing them. The text itself is always the canonical source, readable
and editable with nothing more than a text editor even if HOME itself
disappeared tomorrow.

Think somewhere between Org Mode, Obsidian, and a Unix shell — self-hosted,
family-scale, and small enough for one person to understand end to end.

Design principles, in rough priority order:

- plain text over databases, local files over cloud storage
- simplicity over cleverness, explicit code over abstraction
- one obvious way to do something
- does this naturally extend the existing model, or is it bolting on another system?

---

## What's here today

HOME is a thin Flask shell (`home.py` / `core/`) that auto-mounts small
apps living under `apps/`. Each app owns its own routes and, where it needs
one, its own on-disk storage — there's no shared database beyond user
accounts and sessions.

- **Ark** — a plain-text CLI+web organiser for notes, todos, and events,
  with a deliberately terse query language (`todo, -#work, !<=2`). The
  actual Ark tool is a separate, standalone project
  ([benjaminingreens/ark](https://github.com/benjaminingreens/ark)),
  vendored in here as a git submodule at `apps/ark/vendor` — HOME's job is
  just to give it a web face. Records live in a plain `inbox.txt` per
  workspace until you run `tidy` to sort them into `note/`, `todo/`, `evnt/`.
- **Documents** — a tag-filtered view over your Ark notes.
- **Settings** — change your password; admins can create accounts and reset
  passwords for others.

Accounts are **not** self-service. An admin creates each account with a
default password; new accounts are forced to change it on first login. This
is built for a family/household, not the open internet signing itself up.

---

## Installing HOME on a server

This walks through going from "I have a Linux server with systemd" to "HOME
is running," assuming nothing already exists.

### 1. Prerequisites

- A Linux server with `systemd`, `python3` (3.10+), and `git` installed.
- Enough access to run commands as yourself and `sudo` when needed.

### 2. Install

One command, run on the server:

```bash
curl -fsSL https://raw.githubusercontent.com/benjaminingreens/home/main/install.sh | bash
```

This clones HOME (with the Ark submodule) into `~/apps/homeapp`, builds a
virtualenv, installs dependencies, generates `~/apps/homeapp/.env` with a
random `HOME_SECRET_KEY` and a data directory at `~/apps/homeapp-data`, and
offers to install and start it as a systemd service (`homeapp.service`,
listening on `127.0.0.1:8001` — deliberately not exposed directly; see
step 4).

You can override where things go:

```bash
HOMEAPP_INSTALL_DIR=~/somewhere/else \
  curl -fsSL https://raw.githubusercontent.com/benjaminingreens/home/main/install.sh | bash
```

### 3. Create the first account

HOME needs at least one admin account to create everyone else's. Add these
two lines to `~/apps/homeapp/.env` before first starting the service:

```
HOME_ADMIN_USER=joe
HOME_ADMIN_PASSWORD=a-temporary-password
```

Then (re)start it:

```bash
sudo systemctl restart homeapp
```

On startup, HOME notices `joe` doesn't exist yet and creates it as an admin
with that password, forced to change it on first login. You can remove
those two lines from `.env` afterward — they're only read if the account
doesn't already exist.

### 4. Put it on a real domain

`homeapp` only listens on `127.0.0.1:8001` — it expects a reverse proxy in
front of it for TLS. With nginx, the relevant block looks like:

```nginx
server {
    server_name home.example.com;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    listen 443 ssl;
    ssl_certificate     /etc/letsencrypt/live/home.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/home.example.com/privkey.pem;
}
```

(`certbot --nginx` will set up and manage that certificate for you.) Caddy
works just as well if you'd rather not hand-write TLS config — point it at
`127.0.0.1:8001` and it handles Let's Encrypt automatically. Either way,
port 8001 itself should stay closed to the outside world; only the reverse
proxy needs to be reachable.

### 5. Log in

Visit your domain, log in as `joe` with the temporary password, and you'll
be forced straight to Settings to set a real one. From there, Settings →
create account for anyone else who needs access.

### Updating

Re-run the same install command — it detects the existing checkout, pulls
the latest code (and any Ark submodule update that's been explicitly
bumped — see below), and re-runs the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/benjaminingreens/home/main/install.sh | bash
sudo systemctl restart homeapp
```

Note that bumping to a newer version of Ark itself is a separate,
deliberate step (git submodules pin to a specific commit, not "whatever's
latest") — done in the HOME repo, not on the server.

---

## Running it locally for development

```bash
git clone --recurse-submodules https://github.com/benjaminingreens/home.git
cd home
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 home.py
```

This starts Flask's dev server on `http://127.0.0.1:8000` with debug mode
off by default (set `HOME_DEBUG=1` to turn it on locally). Data defaults to
`/var/lib/home` unless `HOME_DATA_DIR` says otherwise.

---

## Architecture, briefly

```
home.py            entrypoint (dev server)
wsgi.py             entrypoint (gunicorn/production)
core/
    app.py          Flask app, auth enforcement, top-level routes
    apps.py         discovers and mounts everything under apps/
    auth.py, users.py, db.py, workspaces.py, config.py
apps/
    ark/            Ark web integration (routes.py, runner.py, parser.py)
        vendor/     the actual Ark tool, as a git submodule
    documents/
    settings/
templates/, static/  shared layout, CSS, the terminal-style query UI
systemd/, install, install.sh   deployment
```

Each app is mounted automatically from `apps/` — no registry to edit by
hand. Storage is per-user, per-app plain-text workspaces under
`HOME_DATA_DIR/workspaces/<user>/<app>/`; the only database is a small
SQLite file for user accounts and sessions.

---

## Long-term direction

HOME is meant to grow into a small suite of apps sharing this same
philosophy — notes, journal, calendar, contacts, recipes, and so on — each
independent but built on the same plain-text-first model. It's an MVP
today: Ark and Documents work, the deployment story works, and the rest
gets built as it's actually needed rather than speculatively.
