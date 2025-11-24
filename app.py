import os
from datetime import datetime
from flask import Flask, redirect, request, session
from dotenv import load_dotenv

load_dotenv()

from db import SessionLocal, FitbitConnection, init_db
from fitbit.oauth import build_authorize_url, exchange_code_for_tokens

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me")

init_db()


@app.get("/")
def home():
    return "Fitbit Flask Connector is running. Try /connect/fitbit?user_id=demo"

@app.get("/connect/fitbit")
def connect_fitbit():
    """Kick off the OAuth flow. Expects ?user_id=YOUR_INTERNAL_ID"""
    user_id = request.args.get("user_id", "demo")
    session["user_id"] = user_id  # remember across the redirect
    return redirect(build_authorize_url(state=user_id))

@app.get("/oauth/fitbit/callback")
def fitbit_callback():
    code = request.args.get("code")
    state = request.args.get("state")  # (your user_id)

    if not code:
        return "Missing code", 400

    tokens = exchange_code_for_tokens(code)
    fitbit_user_id = tokens["user_id"]
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    scope = tokens.get("scope", "")
    token_type = tokens.get("token_type", "Bearer")
    expires_at = datetime.fromisoformat(tokens["expires_at"])

    user_id = state or session.get("user_id") or "unknown"

    db = SessionLocal()
    try:
        row = db.query(FitbitConnection).filter_by(user_id=user_id).one_or_none()
        if row is None:
            row = FitbitConnection(
                user_id=user_id,
                fitbit_user_id=fitbit_user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                scope=scope,
                token_type=token_type,
                expires_at=expires_at,
                last_synced_at=None,
            )
            db.add(row)
        else:
            row.fitbit_user_id = fitbit_user_id
            row.access_token = access_token
            row.refresh_token = refresh_token
            row.scope = scope
            row.token_type = token_type
            row.expires_at = expires_at
        db.commit()
    finally:
        db.close()

    return "Fitbit connected — you can close this window."

if __name__ == "__main__":
    app.run(port=5000, debug=True)
