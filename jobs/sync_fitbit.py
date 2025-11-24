# jobs/sync_fitbit.py

import os
import sys
import json
from datetime import datetime, timedelta, timezone
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
from fitbit.sync import (
    get_profile,
    get_sleep,
    get_steps,
    get_heartrate,
)

# Optional: posting to mindLAMP
import requests

LAMP_BASE: Optional[str] = os.getenv("LAMP_BASE")  # e.g. https://api.mind.momonia.net or with /api
LAMP_AUTH: Optional[str] = os.getenv("LAMP_AUTH")  # e.g. "Basic XXX" or "Bearer YYY"

# ---- Frequency configuration ----
# You can change these in your .env if you want minute-level instead of hourly:
# FITBIT_STEPS_FREQ=1min
# FITBIT_HR_FREQ=1min
STEPS_FREQ = os.getenv("FITBIT_STEPS_FREQ", "1h")  # "1h" or "1min"
HR_FREQ = os.getenv("FITBIT_HR_FREQ", "1h")        # "1h" or "1min"
SLEEP_FREQ = "daily"  # kept for clarity; get_sleep ignores it but expects a freq param


# ---- Helpers ----

def token_expired(row: FitbitConnection) -> bool:
    """Return True if the access token is expired."""
    expires_at = row.expires_at
    if expires_at is None:
        # Si on n'a pas d'info, on considère le token comme expiré
        return True

    # Si la valeur en DB est naive → on la convertit en aware UTC
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    return now >= expires_at


def send_to_lamp(user_id: str, sensor: str, payload_data) -> None:
    """
    Envoie à mindLAMP un payload déjà 'prêt' (payload_data = UNE mesure).
    1 appel = 1 sensor_event = 1 mesure (dans data).
    """
    if not (LAMP_BASE and LAMP_AUTH):
        print("[WARN] LAMP_BASE or LAMP_AUTH not set. Skipping send.")
        return

    if not payload_data:
        print(f"[{user_id}] skip {sensor}: nothing to send.")
        return

    # Optional: show a tiny sample so you can see what is being sent
    try:
        print(f"[{user_id}] {sensor} sample → {json.dumps(payload_data, ensure_ascii=False)[:400]}")
    except Exception:
        pass

    payload = {
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
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


def send_points_one_by_one(user_id: str, sensor_name: str, points: list) -> None:
    """
    1 point = 1 événement → chaque mesure devient un sensor_event séparé.
    """
    for point in points:
        send_to_lamp(user_id, sensor_name, point)


# ---- Main job ----

def run_once() -> None:
    db = SessionLocal()
    try:
        rows = db.query(FitbitConnection).all()
        if not rows:
            print("No Fitbit connections found. Run the auth flow first.")
            return

        # Date "fin" commune à tous : aujourd'hui (en UTC)
        today = datetime.now(timezone.utc).date()
        end_ymd = today.isoformat()

        for row in rows:
            # 1) Rafraîchir le token si besoin
            if token_expired(row):
                try:
                    new = refresh_tokens(row.refresh_token)
                    row.access_token = new["access_token"]
                    row.refresh_token = new["refresh_token"]
                    # new["expires_at"] est isoformat() sans tz → naive
                    row.expires_at = datetime.fromisoformat(new["expires_at"])
                    db.commit()
                    print(f"[{row.user_id}] token refreshed")
                except Exception as e:
                    print(f"[ERROR] Token refresh failed for {row.user_id}: {e}")
                    continue

            access_token = row.access_token

            # 2) Déterminer la date de début en fonction de last_synced_at
            if row.last_synced_at is None:
                # Premier sync : on prend les 7 derniers jours
                start_date = today - timedelta(days=7)
            else:
                # Sync incrémental : on reprend à partir de la dernière sync
                # (tu peux reculer d'1 jour si tu veux être ultra safe)
                start_date = row.last_synced_at.date()

            start_ymd = start_date.isoformat()

            # 3) Récupérer les données Fitbit sur [start_ymd, end_ymd]
            try:
                profile = get_profile(access_token)

                # Sleep: daily durations
                sleep_raw = get_sleep(access_token, start_ymd, end_ymd, SLEEP_FREQ)

                # Steps: hourly or per-minute totals
                steps_raw = get_steps(access_token, start_ymd, end_ymd, STEPS_FREQ)

                # HR: hourly or per-minute averages
                hr_raw = get_heartrate(access_token, start_ymd, end_ymd, HR_FREQ)
            except Exception as e:
                print(f"[ERROR] Fitbit API error for {row.user_id}: {e}")
                continue

            # 4) Transformer le sleep (date → timestamp) pour avoir "une mesure"
            sleep_points = []
            for s in sleep_raw:
                # s = {"date": "YYYY-MM-DD", "duration_minutes": float}
                try:
                    d = datetime.strptime(s["date"], "%Y-%m-%d").date()
                    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
                    ts = int(dt.timestamp() * 1000)
                    sleep_points.append({
                        "timestamp": ts,
                        "duration_minutes": s["duration_minutes"],
                    })
                except Exception as e:
                    print(f"[WARN] Failed to parse sleep entry {s}: {e}")

            # steps_raw and hr_raw are already lists of points with timestamp
            steps_points = steps_raw          # [{"timestamp":..., "steps":...}, ...]
            hr_points = hr_raw                # [{"timestamp":..., "heartrate":...}, ...]

            # 5) Petit résumé console
            display_name = profile.get("user", {}).get("displayName", "<unknown>")
            print(f"[{row.user_id}] profile: {display_name}")
            print(
                f"[{row.user_id}] counts → steps:{len(steps_points)} "
                f"sleep:{len(sleep_points)} hr:{len(hr_points)}"
            )

            # 6) Envoyer 1 événement par mesure
            if steps_points:
                send_points_one_by_one(row.user_id, "steps", steps_points)
            if sleep_points:
                send_points_one_by_one(row.user_id, "sleep", sleep_points)
            if hr_points:
                send_points_one_by_one(row.user_id, "heartrate", hr_points)

            # 7) Mettre à jour last_synced_at une fois les envois terminés
            row.last_synced_at = datetime.now(timezone.utc)
            db.commit()

    finally:
        db.close()


if __name__ == "__main__":
    run_once()

