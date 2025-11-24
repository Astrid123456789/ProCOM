# Fitbit ↔ Flask Connector (mindLAMP-ready)

A minimal Flask backend that lets users **connect their Fitbit account** and lets your server **pull Fitbit data** (steps, sleep, HR).

> In production, **HTTPS is mandatory**. Fitbit will not redirect to HTTP URLs.

## Quickstart

# edit .env with your FITBIT_CLIENT_ID / SECRET and Redirect URI

```bash
# --- Setup & Run Instructions ---

# 1) Install required dependencies
pip install -r requirements.txt

# 2) Initialize the database (run once)
python -c "from db import init_db; init_db(); print('DB ready')"

# 3) Start the Flask server (keep this terminal open)
python app.py

# 4) In your web browser:
#    Visit http://localhost:5000/connect/fitbit?user_id=<PARTICIPANT_ID>
#    → Log in to Fitbit and click "Allow"
#    → You should see: "Fitbit connected — you can close this window."
#    (Repeat for each participant by changing the user_id)

# 5) Open a second terminal (project root) and run the sync job:
python -m jobs.sync_fitbit

# This will:
# - Fetch Fitbit data (steps, sleep, heart rate)
# - Trim and format the results
# - Post them automatically to your mindLAMP instance
```

## What happens

1. **/connect/fitbit** redirects the user to Fitbit's consent screen.
2. Fitbit calls back **/oauth/fitbit/callback** on your server with `?code=...`.
3. Your server exchanges the code for **access_token + refresh_token** and stores them.
4. A **sync job** fetches Fitbit data using those tokens and writes to your DB.

> Fitbit does **not push health data** to your server. Your server **pulls** it via the Web API after users authorize.

## Files

- `app.py` — Flask routes (`/connect/fitbit`, `/oauth/fitbit/callback`)
- `db.py` — SQLAlchemy models + SQLite
- `fitbit/oauth.py` — OAuth helpers (authorize URL, token exchange, refresh)
- `fitbit/sync.py` — API helpers (profile, steps, sleep, heart rate)
- `jobs/sync_fitbit.py` — one-off sync script (wire to cron in production)
- `.env.example` — copy to `.env` and fill values
- `requirements.txt`

## Production notes

- Serve Flask behind **gunicorn + nginx** or Caddy, with **HTTPS** (Let’s Encrypt).
- Set `.env` `REDIRECT_URI=https://api.mind.momonia.net/oauth/fitbit/callback`.
- Register the same URL in the Fitbit developer console.
- Schedule `jobs/sync_fitbit.py` to run hourly with cron (or use a worker).

## Common pitfalls

- **Invalid redirect_uri** → mismatch between Fitbit console and your `.env`.
- **HTTP instead of HTTPS** in prod → Fitbit rejects the redirect.
- **Not updating refresh_token** after refresh → future calls fail.
- Expecting **intraday HR** without special permission → 403 from Fitbit.

