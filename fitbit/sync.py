import requests

API = "https://api.fitbit.com"

def _auth_headers(access_token: str):
    return {"Authorization": f"Bearer {access_token}"}

def get_profile(access_token: str) -> dict:
    r = requests.get(f"{API}/1/user/-/profile.json",
                     headers=_auth_headers(access_token), timeout=30)
    r.raise_for_status()
    return r.json()

def get_steps_7d(access_token: str) -> dict:
    r = requests.get(f"{API}/1/user/-/activities/steps/date/today/7d.json",
                     headers=_auth_headers(access_token), timeout=30)
    r.raise_for_status()
    return r.json()

def get_sleep_for_date(access_token: str, ymd: str) -> dict:
    r = requests.get(f"{API}/1.2/user/-/sleep/date/{ymd}.json",
                     headers=_auth_headers(access_token), timeout=30)
    r.raise_for_status()
    return r.json()

def get_hr_7d(access_token: str) -> dict:
    r = requests.get(f"{API}/1/user/-/activities/heart/date/today/7d.json",
                     headers=_auth_headers(access_token), timeout=30)
    r.raise_for_status()
    return r.json()


def get_steps_range(access_token: str, start_ymd: str, end_ymd: str) -> dict:
    """
    Récupère les steps jour par jour entre start_ymd et end_ymd (YYYY-MM-DD).
    """
    r = requests.get(
        f"{API}/1/user/-/activities/steps/date/{start_ymd}/{end_ymd}.json",
        headers=_auth_headers(access_token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_hr_range(access_token: str, start_ymd: str, end_ymd: str) -> dict:
    """
    Récupère le heart rate journalié entre start_ymd et end_ymd.
    """
    r = requests.get(
        f"{API}/1/user/-/activities/heart/date/{start_ymd}/{end_ymd}.json",
        headers=_auth_headers(access_token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def get_sleep_range(access_token: str, start_ymd: str, end_ymd: str) -> dict:
    r = requests.get(
        f"{API}/1.2/user/-/sleep/date/{start_ymd}/{end_ymd}.json",
        headers=_auth_headers(access_token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
