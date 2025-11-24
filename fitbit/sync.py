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
