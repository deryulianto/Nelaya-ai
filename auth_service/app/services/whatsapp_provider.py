import os

WA_PROVIDER = os.getenv("WA_PROVIDER", "mock")
WA_DEV_SHOW_OTP = os.getenv("WA_DEV_SHOW_OTP", "1") == "1"

def send_whatsapp_otp(phone_e164: str, otp: str) -> None:
    if WA_PROVIDER == "mock":
        if WA_DEV_SHOW_OTP:
            print(f"[WA-MOCK] Send OTP to {phone_e164}: {otp}")
        else:
            print(f"[WA-MOCK] Send OTP to {phone_e164}: (hidden)")
        return
    raise RuntimeError("WA_PROVIDER=prod not implemented yet")
