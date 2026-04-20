"""Google OAuth authentication — verify ID tokens and manage users."""

import json
import os
import sqlite3

import requests
from fastapi import Request

from src.config import SESSION_DB_PATH

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


def _get_db():
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            picture TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def verify_google_token(id_token: str) -> dict | None:
    """Verify a Google ID token using Google's tokeninfo endpoint.

    Returns user info dict {sub, email, name, picture} or None if invalid.
    """
    try:
        # Use Google's tokeninfo endpoint (no library needed)
        resp = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
            timeout=5,
        )
        if resp.status_code != 200:
            return None

        payload = resp.json()

        # Verify audience if client ID is configured
        if GOOGLE_CLIENT_ID and payload.get("aud") != GOOGLE_CLIENT_ID:
            return None

        return {
            "sub": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name", payload.get("email", "").split("@")[0]),
            "picture": payload.get("picture", ""),
        }
    except Exception:
        return None


def get_or_create_user(user_info: dict) -> dict:
    """Create user if not exists, return user record."""
    conn = _get_db()

    # Check if user exists
    cursor = conn.execute("SELECT id, email, name, picture FROM users WHERE id = ?", (user_info["sub"],))
    row = cursor.fetchone()

    if row:
        # Update name/picture in case they changed
        conn.execute(
            "UPDATE users SET name = ?, picture = ? WHERE id = ?",
            (user_info["name"], user_info["picture"], user_info["sub"]),
        )
        conn.commit()
        conn.close()
        return {"id": row[0], "email": row[1], "name": user_info["name"], "picture": user_info["picture"]}

    # Create new user
    conn.execute(
        "INSERT INTO users (id, email, name, picture) VALUES (?, ?, ?, ?)",
        (user_info["sub"], user_info["email"], user_info["name"], user_info["picture"]),
    )
    conn.commit()
    conn.close()
    return {
        "id": user_info["sub"],
        "email": user_info["email"],
        "name": user_info["name"],
        "picture": user_info["picture"],
    }


def get_current_user(request: Request) -> dict | None:
    """Extract user from Authorization header (Bearer token = Google sub ID)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None

    token = auth[7:]
    conn = _get_db()
    cursor = conn.execute("SELECT id, email, name, picture FROM users WHERE id = ?", (token,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"id": row[0], "email": row[1], "name": row[2], "picture": row[3]}
    return None
