# app/services/user_store.py
import os
import sqlite3
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, timezone

DB_PATH = os.getenv("AUTH_DB_PATH", "data/auth.db")

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      phone_e164 TEXT UNIQUE NOT NULL,
      name TEXT,
      landing_port TEXT,
      gear_subtype TEXT,
      vessel_gt_class TEXT DEFAULT 'GT_5_10',
      trip_hours_default REAL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS otp_requests (
      phone_e164 TEXT PRIMARY KEY,
      otp_hash TEXT,
      expires_at TEXT,
      attempts INTEGER DEFAULT 0,
      send_count INTEGER DEFAULT 0,
      last_sent_at TEXT,
      locked_until TEXT
    )
    """)
    conn.commit()
    conn.close()

def get_user_by_phone(phone_e164: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE phone_e164=?", (phone_e164,)).fetchone()
    conn.close()
    return dict(row) if row else None

def upsert_user(phone_e164: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_conn()
    existing = conn.execute("SELECT * FROM users WHERE phone_e164=?", (phone_e164,)).fetchone()
    now = _utcnow_iso()

    if existing:
        cols = []
        vals = []
        for k, v in updates.items():
            cols.append(f"{k}=?")
            vals.append(v)
        cols.append("updated_at=?")
        vals.append(now)
        vals.append(phone_e164)
        conn.execute(f"UPDATE users SET {', '.join(cols)} WHERE phone_e164=?", tuple(vals))
    else:
        conn.execute("""
        INSERT INTO users (phone_e164, name, landing_port, gear_subtype, vessel_gt_class, trip_hours_default, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            phone_e164,
            updates.get("name"),
            updates.get("landing_port"),
            updates.get("gear_subtype"),
            updates.get("vessel_gt_class", "GT_5_10"),
            updates.get("trip_hours_default"),
            now, now
        ))

    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE phone_e164=?", (phone_e164,)).fetchone()
    conn.close()
    return dict(user)

def get_otp_state(phone_e164: str) -> Dict[str, Any]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM otp_requests WHERE phone_e164=?", (phone_e164,)).fetchone()
    conn.close()
    return dict(row) if row else {}

def upsert_otp_state(phone_e164: str, state: Dict[str, Any]) -> None:
    conn = get_conn()
    existing = conn.execute("SELECT * FROM otp_requests WHERE phone_e164=?", (phone_e164,)).fetchone()

    fields = ["otp_hash", "expires_at", "attempts", "send_count", "last_sent_at", "locked_until"]
    vals = [state.get(f) for f in fields]

    if existing:
        conn.execute("""
          UPDATE otp_requests
          SET otp_hash=?, expires_at=?, attempts=?, send_count=?, last_sent_at=?, locked_until=?
          WHERE phone_e164=?
        """, (*vals, phone_e164))
    else:
        conn.execute("""
          INSERT INTO otp_requests (phone_e164, otp_hash, expires_at, attempts, send_count, last_sent_at, locked_until)
          VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (phone_e164, *vals))

    conn.commit()
    conn.close()
