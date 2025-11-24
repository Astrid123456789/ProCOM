import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any

API = "https://api.fitbit.com"

# -------------------------------------------------------------------
# Auth header
# -------------------------------------------------------------------

def _auth(access_token: str) -> Dict[str, str]:
    """Build the Authorization header for Fitbit API calls."""
    return {"Authorization": f"Bearer {access_token}"}


# -------------------------------------------------------------------
# Profile
# -------------------------------------------------------------------

def get_profile(access_token: str) -> Dict[str, Any]:
    """Get the Fitbit user profile."""
    url = f"{API}/1/user/-/profile.json"
    r = requests.get(url, headers=_auth(access_token), timeout=30)
    r.raise_for_status()
    return r.json()


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _combine_datetime(ymd: str, time_str: str) -> datetime:
    """Combine a YYYY-MM-DD date string and HH:MM:SS time string into a datetime."""
    d = datetime.strptime(ymd, "%Y-%m-%d").date()
    t = datetime.strptime(time_str, "%H:%M:%S").time()
    return datetime.combine(d, t)

def _floor_to_hour(dt: datetime) -> datetime:
    """Floor a datetime to the start of the hour."""
    return dt.replace(minute=0, second=0, microsecond=0)


# -------------------------------------------------------------------
# SLEEP  (daily only — Fitbit does not support intraday sleep duration
#         in a straightforward way, so we work with daily totals)
# -------------------------------------------------------------------

def get_sleep(access_token: str, start_ymd: str, end_ymd: str, freq: str) -> List[Dict[str, Any]]:
    """
    Sleep duration per day between start_ymd and end_ymd (inclusive).

    freq is ignored for sleep because Fitbit only supports daily sleep duration.

    Returns:
        [
          {"date": "2025-11-10", "duration_minutes": 421.0},
          ...
        ]
    """
    url = f"{API}/1.2/user/-/sleep/date/{start_ymd}/{end_ymd}.json"
    r = requests.get(url, headers=_auth(access_token), timeout=30)
    r.raise_for_status()
    raw = r.json()

    by_day: Dict[str, int] = {}

    for entry in raw.get("sleep", []):
        d = entry.get("dateOfSleep")
        dur = entry.get("duration", 0)  # ms
        if d:
            by_day[d] = by_day.get(d, 0) + int(dur)

    results: List[Dict[str, Any]] = []
    for d, ms in sorted(by_day.items()):
        results.append({
            "date": d,
            "duration_minutes": ms / 1000 / 60,  # convert ms → minutes
        })

    return results


# -------------------------------------------------------------------
# STEPS (intraday 1-minute → aggregated depending on freq)
# -------------------------------------------------------------------

def get_steps(access_token: str, start_ymd: str, end_ymd: str, freq: str) -> List[Dict[str, Any]]:
    """
    Get steps between start_ymd and end_ymd.

    freq: "1min" or "1h"

    Returns:
        - "1min" → [{"timestamp": ..., "steps": value}, ...]
        - "1h"   → [{"timestamp": ..., "steps": sum_per_hour}, ...]
    """
    all_points: List[Dict[str, Any]] = []
    current = datetime.strptime(start_ymd, "%Y-%m-%d").date()
    end = datetime.strptime(end_ymd, "%Y-%m-%d").date()

    while current <= end:
        day = current.isoformat()
        url = f"{API}/1/user/-/activities/steps/date/{day}/1d/1min.json"
        r = requests.get(url, headers=_auth(access_token), timeout=30)
        r.raise_for_status()
        raw = r.json()

        dataset = raw.get("activities-steps-intraday", {}).get("dataset", [])

        if freq == "1min":
            for entry in dataset:
                dt = _combine_datetime(day, entry["time"])
                ts = int(dt.timestamp() * 1000)
                all_points.append({
                    "timestamp": ts,
                    "steps": entry["value"],
                })

        elif freq == "1h":
            hourly: Dict[datetime, int] = {}
            for entry in dataset:
                dt = _combine_datetime(day, entry["time"])
                h = _floor_to_hour(dt)
                hourly[h] = hourly.get(h, 0) + entry["value"]

            for hdt, total in sorted(hourly.items()):
                ts = int(hdt.timestamp() * 1000)
                all_points.append({
                    "timestamp": ts,
                    "steps": total,
                })

        current += timedelta(days=1)

    return all_points


# -------------------------------------------------------------------
# HEART RATE (intraday 1-minute → aggregated depending on freq)
# -------------------------------------------------------------------

def get_heartrate(access_token: str, start_ymd: str, end_ymd: str, freq: str) -> List[Dict[str, Any]]:
    """
    Get heart rate between start_ymd and end_ymd.

    freq: "1min" or "1h"

    Returns:
        - "1min" → [{"timestamp": ..., "heartrate": bpm}, ...]
        - "1h"   → [{"timestamp": ..., "heartrate": avg_bpm_for_hour}, ...]
    """
    all_points: List[Dict[str, Any]] = []
    current = datetime.strptime(start_ymd, "%Y-%m-%d").date()
    end = datetime.strptime(end_ymd, "%Y-%m-%d").date()

    while current <= end:
        day = current.isoformat()
        url = f"{API}/1/user/-/activities/heart/date/{day}/1d/1min.json"
        r = requests.get(url, headers=_auth(access_token), timeout=30)
        r.raise_for_status()
        raw = r.json()

        dataset = raw.get("activities-heart-intraday", {}).get("dataset", [])

        if freq == "1min":
            for entry in dataset:
                dt = _combine_datetime(day, entry["time"])
                ts = int(dt.timestamp() * 1000)
                all_points.append({
                    "timestamp": ts,
                    "heartrate": entry["value"],
                })

        elif freq == "1h":
            sums: Dict[datetime, int] = {}
            counts: Dict[datetime, int] = {}

            for entry in dataset:
                dt = _combine_datetime(day, entry["time"])
                h = _floor_to_hour(dt)
                sums[h] = sums.get(h, 0) + entry["value"]
                counts[h] = counts.get(h, 0) + 1

            for hdt in sorted(sums.keys()):
                avg = sums[hdt] / counts[hdt]
                ts = int(hdt.timestamp() * 1000)
                all_points.append({
                    "timestamp": ts,
                    "heartrate": avg,
                })

        current += timedelta(days=1)

    return all_points


