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

from datetime import datetime, timedelta

today = datetime.utcnow().date()

if row.last_synced_at is None:
    # Premier sync : on prend par exemple les 7 derniers jours
    start_date = today - timedelta(days=7)
else:
    # Sync incrémental : on reprend à partir du dernier sync
    # On peut éventuellement reculer d'1 jour pour être safe
    start_date = row.last_synced_at.date()  # ou row.last_synced_at.date() - timedelta(days=1)

start_ymd = start_date.strftime("%Y-%m-%d")
end_ymd = today.strftime("%Y-%m-%d")

# ---- Helpers pour envoyer 1 événement par mesure (avec batching) ----

def chunked(iterable, size):
    """Coupe une liste en paquets de taille 'size'."""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]

def send_points_in_batches(user_id: str, sensor_name: str, points: list, batch_size: int = 200):
    """
    Envoie les mesures vers mindLAMP par paquets.
    Chaque élément de 'points' est une mesure du capteur.
    """
    for batch in chunked(points, batch_size):
        # Ici 'batch' est une liste de mesures.
        # Si send_to_lamp attend déjà une liste d'événements, c'est parfait.
        send_to_lamp(user_id, sensor_name, batch)

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

        # Date "fin" commune à tous : aujourd'hui (en UTC)
        today = datetime.utcnow().date()
        end_ymd = today.isoformat()

        for row in rows:
            # 1) Rafraîchir le token si besoin
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

            access_token = row.access_token

            # 2) Déterminer la date de début en fonction de last_synced_at
            if row.last_synced_at is None:
                # Premier sync : on prend par exemple les 7 derniers jours
                start_date = today - timedelta(days=7)
            else:
                # Sync incrémental : on reprend à partir de la dernière sync
                # (tu peux reculer d'1 jour si tu veux être ultra safe)
                start_date = row.last_synced_at.date()

            start_ymd = start_date.isoformat()

            # 3) Récupérer les données Fitbit sur [start_ymd, end_ymd]
            try:
                profile = get_profile(access_token)
                steps_raw = get_steps_range(access_token, start_ymd, end_ymd)
                sleep_raw = get_sleep_range(access_token, start_ymd, end_ymd)
                hr_raw    = get_hr_range(access_token, start_ymd, end_ymd)
            except Exception as e:
                print(f"[ERROR] Fitbit API error for {row.user_id}: {e}")
                continue

            # 4) Transformer les bruts Fitbit en listes de points "plats"
            #    (en supposant que _trim_fitbit(type, raw) renvoie une liste de mesures)
            steps = _trim_fitbit("steps", steps_raw)
            sleep = _trim_fitbit("sleep", sleep_raw)
            hr    = _trim_fitbit("heartrate", hr_raw)

            # 5) Petit résumé console
            display_name = profile.get("user", {}).get("displayName", "<unknown>")
            print(f"[{row.user_id}] profile: {display_name}")
            print(
                f"[{row.user_id}] counts → steps:{len(steps)} "
                f"sleep:{len(sleep)} hr:{len(hr)}"
            )

            # 6) Envoyer 1 événement par mesure (par paquets)
            if steps:
                send_points_in_batches(row.user_id, "steps", steps)
            if sleep:
                send_points_in_batches(row.user_id, "sleep", sleep)
            if hr:
                send_points_in_batches(row.user_id, "heartrate", hr)

            # 7) Mettre à jour last_synced_at une fois les envois terminés
            row.last_synced_at = datetime.utcnow()
            db.commit()

    finally:
        db.close()

if __name__ == "__main__":
    run_once()
