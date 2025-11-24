# jobs/sync_fitbit.py

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Optional

# Make sure imports work whether you run from project root or jobs/ 
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Env loading
from dotenv import load_dotenv
load_dotenv()  # loads .env from project root

# Local modules 
from db import SessionLocal, FitbitConnection
from fitbit.oauth import refresh_tokens
from fitbit.sync import get_profile, get_steps_7d, get_sleep_for_date, get_hr_7d

# Optional: posting to mindLAMP 
import requests

LAMP_BASE: Optional[str] = os.getenv("LAMP_BASE")  # e.g. https://api.mind.momonia.net or with /api
LAMP_AUTH: Optional[str] = os.getenv("LAMP_AUTH")  # e.g. "Basic XXX" or "Bearer YYY"

def token_expired(row: FitbitConnection) -> bool:
    """Return True if the access token is expired."""
    return datetime.utcnow() >= row.expires_at.replace(tzinfo=None)

def _trim_fitbit(sensor: str, data: dict):
    """Return just the meaningful array for each Fitbit dataset."""
    if sensor == "steps":
        return data.get("activities-steps", [])
    if sensor == "sleep":
        return data.get("sleep", [])
    if sensor == "heartrate":
        return data.get("activities-heart", [])
    return data

def send_to_lamp(user_id: str, sensor: str, data: dict) -> None:
    """
    Send only the relevant Fitbit arrays to mindLAMP, if LAMP_BASE and LAMP_AUTH are configured.
    Skip sending when there's nothing to send.
    """
    if not (LAMP_BASE and LAMP_AUTH):
        print("[WARN] LAMP_BASE or LAMP_AUTH not set. Skipping send.")
        return

    payload_data = _trim_fitbit(sensor, data)

    if not payload_data:
        print(f"[{user_id}] skip {sensor}: Fitbit returned no data to send.")
        return

    # Optional: show a tiny sample so you can see what is being sent
    try:
        sample = payload_data[:1] if isinstance(payload_data, list) else payload_data
        print(f"[{user_id}] {sensor} sample → {json.dumps(sample, ensure_ascii=False)[:400]}")
    except Exception:
        pass

    payload = {
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
        "sensor": f"fitbit_{sensor}",
        "data": payload_data,
    }

    url = f"{LAMP_BASE}/participant/{user_id}/sensor_event"
    headers = {
        "Authorization": LAMP_AUTH,
        "Content-Type": "application/json",
    }

    print(f"POST {url}")
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"LAMP POST {sensor} for {user_id} → {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"[WARN] Failed to POST {sensor} to LAMP for {user_id}: {e}")

def run_once() -> None:
    db = SessionLocal()
    try:
        rows = db.query(FitbitConnection).all()
        if not rows:
            print("No Fitbit connections found. Run the auth flow first.")
            return

        for row in rows:
            # Refresh token if needed
            if token_expired(row):
                try:
                    new = refresh_tokens(row.refresh_token)
                    row.access_token = new["access_token"]
                    row.refresh_token = new["refresh_token"]
                    row.expires_at = datetime.fromisoformat(new["expires_at"])
                    db.commit()
                    print(f"[{row.user_id}] token refreshed")
                except Exception as e:
                    print(f"[ERROR] Token refresh failed for {row.user_id}: {e}")
                    continue

            access = row.access_token

            # Fetch data
            try:
                profile = get_profile(access)
                steps = get_steps_7d(access)
                # Sleep: query yesterday (today is often empty)
                yday = (datetime.utcnow() - timedelta(days=1)).date().isoformat()
                sleep = get_sleep_for_date(access, yday)
                hr = get_hr_7d(access)
            except Exception as e:
                print(f"[ERROR] Fitbit API error for {row.user_id}: {e}")
                continue

            # Print quick summary + counts so you SEE if it's empty or not
            display_name = profile.get("user", {}).get("displayName", "<unknown>")
            steps_arr = _trim_fitbit("steps", steps)
            sleep_arr = _trim_fitbit("sleep", sleep)
            hr_arr    = _trim_fitbit("heartrate", hr)

            print(f"[{row.user_id}] profile: {display_name}")
            print(f"[{row.user_id}] counts → steps:{len(steps_arr)} sleep:{len(sleep_arr)} hr:{len(hr_arr)}")

            # Update last sync
            row.last_synced_at = datetime.utcnow()
            db.commit()

            # Send only non-empty datasets
            send_to_lamp(row.user_id, "steps", steps)
            send_to_lamp(row.user_id, "sleep", sleep)
            send_to_lamp(row.user_id, "heartrate", hr)

    finally:
        db.close()

if __name__ == "__main__":
    run_once()
