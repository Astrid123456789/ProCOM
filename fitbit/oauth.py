import os, base64, urllib.parse, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL = "https://api.fitbit.com/oauth2/token"

# Use os.getenv() so it doesn’t crash if .env isn’t loaded yet
CLIENT_ID = os.getenv("FITBIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("FITBIT_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
SCOPES = os.getenv("SCOPES", "activity sleep heartrate profile")

# Optional: helpful check for missing values
if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URI:
    raise RuntimeError(
        "Missing Fitbit environment variables. Make sure your .env file "
        "contains FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET, and REDIRECT_URI."
    )


def build_authorize_url(state: str):
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "prompt": "consent",
        "state": state,
        "expires_in": "604800",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

def _basic_auth_header():
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {basic}"}

def exchange_code_for_tokens(code: str):
    data = {
        "client_id": CLIENT_ID,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }
    r = requests.post(TOKEN_URL,
                      headers={**_basic_auth_header(),
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data=data, timeout=30)
    r.raise_for_status()
    payload = r.json()
    payload["expires_at"] = (datetime.utcnow() + timedelta(seconds=payload["expires_in"])).isoformat()
    return payload

def refresh_tokens(refresh_token: str):
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    r = requests.post(TOKEN_URL,
                      headers={**_basic_auth_header(),
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data=data, timeout=30)
    r.raise_for_status()
    payload = r.json()
    payload["expires_at"] = (datetime.utcnow() + timedelta(seconds=payload["expires_in"])).isoformat()
    return payload
