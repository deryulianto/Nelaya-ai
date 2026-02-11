import random
from datetime import datetime, timedelta, timezone

from auth_service.app.services.user_store import get_otp_state, upsert_otp_state
from auth_service.app.services.whatsapp_provider import send_whatsapp_otp
from auth_service.app.utils.security import hash_otp

OTP_TTL_MIN = 5
MAX_SEND_PER_HOUR = 3
MAX_VERIFY_ATTEMPTS = 3
LOCK_MIN = 15

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)

def request_otp(phone_e164: str) -> None:
    st = get_otp_state(phone_e164) or {}
    now = _utcnow()

    if st.get("locked_until"):
        lu = _parse_iso(st["locked_until"])
        if lu > now:
            raise ValueError("Terlalu banyak percobaan. Coba lagi nanti.")

    send_count = int(st.get("send_count") or 0)
    if st.get("last_sent_at"):
        ls = _parse_iso(st["last_sent_at"])
        if now - ls > timedelta(hours=1):
            send_count = 0

    if send_count >= MAX_SEND_PER_HOUR:
        raise ValueError("Terlalu sering minta OTP. Coba lagi nanti.")

    otp = f"{random.randint(0, 999999):06d}"
    otp_h = hash_otp(phone_e164, otp)
    expires_at = (now + timedelta(minutes=OTP_TTL_MIN)).isoformat()

    upsert_otp_state(phone_e164, {
        "otp_hash": otp_h,
        "expires_at": expires_at,
        "attempts": 0,
        "send_count": send_count + 1,
        "last_sent_at": now.isoformat(),
        "locked_until": None,
    })

    send_whatsapp_otp(phone_e164, otp)

def verify_otp(phone_e164: str, otp: str) -> None:
    st = get_otp_state(phone_e164) or {}
    now = _utcnow()

    if st.get("locked_until") and _parse_iso(st["locked_until"]) > now:
        raise ValueError("Akun terkunci sementara. Coba lagi nanti.")

    if not st.get("expires_at"):
        raise ValueError("OTP belum diminta.")
    if _parse_iso(st["expires_at"]) < now:
        raise ValueError("OTP sudah kedaluwarsa. Minta OTP baru.")

    attempts = int(st.get("attempts") or 0)
    if attempts >= MAX_VERIFY_ATTEMPTS:
        upsert_otp_state(phone_e164, {**st, "locked_until": (now + timedelta(minutes=LOCK_MIN)).isoformat()})
        raise ValueError("Terlalu banyak salah. Dikunci sementara.")

    if hash_otp(phone_e164, otp) != st.get("otp_hash"):
        attempts += 1
        new_state = dict(st)
        new_state["attempts"] = attempts
        if attempts >= MAX_VERIFY_ATTEMPTS:
            new_state["locked_until"] = (now + timedelta(minutes=LOCK_MIN)).isoformat()
        upsert_otp_state(phone_e164, new_state)
        raise ValueError("OTP salah.")

    upsert_otp_state(phone_e164, {**st, "attempts": 0, "locked_until": None})
