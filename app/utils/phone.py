# app/utils/phone.py
import re

def normalize_phone_e164(phone: str) -> str:
    """
    Normalize Indonesian phone numbers to E.164 (+62...).
    Accepts: 0812..., 62812..., +62812...
    """
    if not phone:
        raise ValueError("phone is empty")

    s = phone.strip()
    s = re.sub(r"[^\d+]", "", s)  # keep digits and '+'

    if s.startswith("+"):
        # +62...
        if not s.startswith("+62"):
            raise ValueError("only +62 numbers supported in v0")
        digits = re.sub(r"\D", "", s[1:])
        out = "+" + digits
    else:
        digits = re.sub(r"\D", "", s)
        if digits.startswith("0"):
            out = "+62" + digits[1:]
        elif digits.startswith("62"):
            out = "+62" + digits[2:]
        else:
            # assume local missing 0, e.g. 812...
            out = "+62" + digits

    # Basic sanity checks
    if not out.startswith("+62"):
        raise ValueError("invalid phone after normalization")
    if len(out) < 10 or len(out) > 16:
        raise ValueError("phone length out of range")

    return out
