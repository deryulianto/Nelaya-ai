import os, hmac, hashlib, base64, time, json

OTP_SECRET = os.getenv("OTP_SECRET", "dev-otp-secret-change-me")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-secret-change-me")

def hash_otp(phone_e164: str, otp: str) -> str:
    msg = f"{phone_e164}:{otp}".encode("utf-8")
    key = OTP_SECRET.encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def _b64url_json(obj: dict) -> str:
    return _b64url(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))

def sign_jwt(payload: dict, exp_seconds: int = 7 * 24 * 3600) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    body = dict(payload)
    body["iat"] = now
    body["exp"] = now + int(exp_seconds)

    signing_input = f"{_b64url_json(header)}.{_b64url_json(body)}".encode("utf-8")
    sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return signing_input.decode("utf-8") + "." + _b64url(sig)

def verify_jwt(token: str) -> dict:
    h, p, s = token.split(".")
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = base64.urlsafe_b64decode(s + "==")
    expected = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("bad signature")

    payload = json.loads(base64.urlsafe_b64decode(p + "==").decode("utf-8"))
    now = int(time.time())
    if int(payload.get("exp", 0)) < now:
        raise ValueError("token expired")
    return payload
